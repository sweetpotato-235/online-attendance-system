import os
from datetime import date, datetime, timedelta
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-before-deployment")
database_url = os.environ.get("DATABASE_URL", "").strip()
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///attendance.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin or teacher
    active = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class SchoolClass(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), nullable=False)
    section = db.Column(db.String(20), nullable=False, default="A")
    __table_args__ = (db.UniqueConstraint("name", "section", name="uq_class_section"),)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admission_no = db.Column(db.String(40), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    school_class = db.relationship("SchoolClass", backref="students")


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    attendance_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(12), nullable=False)
    marked_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    student = db.relationship("Student", backref="attendance_records")
    marker = db.relationship("User")
    __table_args__ = (db.UniqueConstraint("student_id", "attendance_date", name="uq_student_day"),)


def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user or not user.active:
                session.clear()
                flash("Please sign in to continue.", "warning")
                return redirect(url_for("login"))
            if role and user.role != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.context_processor
def inject_user():
    return {"signed_in_user": current_user(), "today": date.today()}


@app.cli.command("init-db")
def init_db_command():
    """Create database tables."""
    with app.app_context():
        db.create_all()
    print("Database tables created.")


@app.cli.command("create-admin")
def create_admin_command():
    """Create an administrator using ADMIN_USERNAME and ADMIN_PASSWORD environment variables."""
    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if not username or not password:
        raise SystemExit("Set ADMIN_USERNAME and ADMIN_PASSWORD before running this command.")
    if len(password) < 12:
        raise SystemExit("ADMIN_PASSWORD must be at least 12 characters.")
    with app.app_context():
        db.create_all()
        existing = User.query.filter_by(username=username).first()
        if existing:
            existing.role = "admin"
            existing.active = True
            existing.set_password(password)
        else:
            user = User(username=username, role="admin")
            user.set_password(password)
            db.session.add(user)
        db.session.commit()
    print("Administrator account created/updated.")


@app.route("/")
def index():
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username, active=True).first()
        if user and user.check_password(password):
            session.clear()
            session["user_id"] = user.id
            session.permanent = True
            flash("Welcome back.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required()
def dashboard():
    user = current_user()
    student_count = Student.query.filter_by(active=True).count()
    class_count = SchoolClass.query.count()
    today_count = Attendance.query.filter_by(attendance_date=date.today()).count()
    present_today = Attendance.query.filter_by(attendance_date=date.today(), status="Present").count()
    recent = Attendance.query.order_by(Attendance.attendance_date.desc(), Attendance.id.desc()).limit(8).all()
    return render_template("dashboard.html", user=user, student_count=student_count,
                           class_count=class_count, today_count=today_count,
                           present_today=present_today, recent=recent)


@app.route("/students", methods=["GET", "POST"])
@login_required("admin")
def students():
    classes = SchoolClass.query.order_by(SchoolClass.name, SchoolClass.section).all()
    if request.method == "POST":
        admission_no = request.form.get("admission_no", "").strip()
        full_name = request.form.get("full_name", "").strip()
        class_id = request.form.get("class_id", type=int)
        if not admission_no or not full_name or not class_id or not db.session.get(SchoolClass, class_id):
            flash("Enter all student details and select a valid class.", "danger")
        elif Student.query.filter_by(admission_no=admission_no).first():
            flash("That admission number already exists.", "danger")
        else:
            db.session.add(Student(admission_no=admission_no, full_name=full_name, class_id=class_id))
            db.session.commit()
            flash("Student added successfully.", "success")
            return redirect(url_for("students"))
    q = request.args.get("q", "").strip()
    class_filter = request.args.get("class_id", type=int)
    query = Student.query.join(SchoolClass).filter(Student.active.is_(True))
    if q:
        query = query.filter(db.or_(Student.full_name.ilike(f"%{q}%"), Student.admission_no.ilike(f"%{q}%")))
    if class_filter:
        query = query.filter(Student.class_id == class_filter)
    rows = query.order_by(SchoolClass.name, SchoolClass.section, Student.full_name).all()
    return render_template("students.html", students=rows, classes=classes, q=q, class_filter=class_filter)


@app.route("/students/<int:student_id>/toggle", methods=["POST"])
@login_required("admin")
def toggle_student(student_id):
    student = db.get_or_404(Student, student_id)
    student.active = not student.active
    db.session.commit()
    flash("Student status updated.", "success")
    return redirect(url_for("students"))


@app.route("/classes", methods=["GET", "POST"])
@login_required("admin")
def classes():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        section = request.form.get("section", "A").strip().upper()
        if not name or not section:
            flash("Class and section are required.", "danger")
        elif SchoolClass.query.filter_by(name=name, section=section).first():
            flash("That class and section already exist.", "danger")
        else:
            db.session.add(SchoolClass(name=name, section=section))
            db.session.commit()
            flash("Class/section added.", "success")
            return redirect(url_for("classes"))
    rows = SchoolClass.query.order_by(SchoolClass.name, SchoolClass.section).all()
    return render_template("classes.html", classes=rows)


@app.route("/teachers", methods=["GET", "POST"])
@login_required("admin")
def teachers():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or len(password) < 12:
            flash("Username is required and password must be at least 12 characters.", "danger")
        elif User.query.filter_by(username=username).first():
            flash("That username already exists.", "danger")
        else:
            teacher = User(username=username, role="teacher")
            teacher.set_password(password)
            db.session.add(teacher)
            db.session.commit()
            flash("Teacher account created.", "success")
            return redirect(url_for("teachers"))
    rows = User.query.filter_by(role="teacher").order_by(User.username).all()
    return render_template("teachers.html", teachers=rows)


@app.route("/teachers/<int:user_id>/toggle", methods=["POST"])
@login_required("admin")
def toggle_teacher(user_id):
    teacher = db.get_or_404(User, user_id)
    if teacher.role != "teacher":
        abort(400)
    teacher.active = not teacher.active
    db.session.commit()
    flash("Teacher account status updated.", "success")
    return redirect(url_for("teachers"))


@app.route("/attendance", methods=["GET", "POST"])
@login_required()
def attendance():
    classes = SchoolClass.query.order_by(SchoolClass.name, SchoolClass.section).all()
    selected_class = request.values.get("class_id", type=int)
    selected_date_text = request.values.get("attendance_date", date.today().isoformat())
    try:
        selected_date = date.fromisoformat(selected_date_text)
    except ValueError:
        selected_date = date.today()
        flash("Invalid date; showing today.", "warning")

    if request.method == "POST":
        if not selected_class or not db.session.get(SchoolClass, selected_class):
            flash("Select a valid class and section.", "danger")
            return redirect(url_for("attendance"))
        students_in_class = Student.query.filter_by(class_id=selected_class, active=True).all()
        if not students_in_class:
            flash("There are no active students in this class.", "warning")
            return redirect(url_for("attendance", class_id=selected_class, attendance_date=selected_date.isoformat()))
        for student in students_in_class:
            status = request.form.get(f"status_{student.id}")
            if status not in {"Present", "Absent", "On Leave"}:
                continue
            record = Attendance.query.filter_by(student_id=student.id, attendance_date=selected_date).first()
            if record:
                record.status = status
                record.marked_by = current_user().id
            else:
                db.session.add(Attendance(student_id=student.id, attendance_date=selected_date,
                                          status=status, marked_by=current_user().id))
        db.session.commit()
        flash(f"Attendance saved for {selected_date.isoformat()}.", "success")
        return redirect(url_for("attendance", class_id=selected_class, attendance_date=selected_date.isoformat()))

    roster = []
    if selected_class:
        class_obj = db.session.get(SchoolClass, selected_class)
        if class_obj:
            roster = Student.query.filter_by(class_id=selected_class, active=True).order_by(Student.full_name).all()
    records = {}
    if roster:
        ids = [s.id for s in roster]
        records = {r.student_id: r.status for r in Attendance.query.filter(
            Attendance.student_id.in_(ids), Attendance.attendance_date == selected_date).all()}
    return render_template("attendance.html", classes=classes, selected_class=selected_class,
                           selected_date=selected_date, roster=roster, records=records)


@app.route("/reports")
@login_required()
def reports():
    start_text = request.args.get("start", date.today().replace(day=1).isoformat())
    end_text = request.args.get("end", date.today().isoformat())
    class_filter = request.args.get("class_id", type=int)
    q = request.args.get("q", "").strip()
    try:
        start_date, end_date = date.fromisoformat(start_text), date.fromisoformat(end_text)
    except ValueError:
        start_date, end_date = date.today().replace(day=1), date.today()
        flash("Invalid date range.", "warning")
    classes = SchoolClass.query.order_by(SchoolClass.name, SchoolClass.section).all()
    query = Student.query.join(SchoolClass).filter(Student.active.is_(True))
    if class_filter:
        query = query.filter(Student.class_id == class_filter)
    if q:
        query = query.filter(db.or_(Student.full_name.ilike(f"%{q}%"), Student.admission_no.ilike(f"%{q}%")))
    roster = query.order_by(SchoolClass.name, SchoolClass.section, Student.full_name).all()
    report_rows = []
    for student in roster:
        records = Attendance.query.filter(Attendance.student_id == student.id,
                                          Attendance.attendance_date >= start_date,
                                          Attendance.attendance_date <= end_date).all()
        total = len(records)
        present = sum(1 for r in records if r.status == "Present")
        absent = sum(1 for r in records if r.status == "Absent")
        leave = sum(1 for r in records if r.status == "On Leave")
        percentage = (present / total * 100) if total else 0
        report_rows.append({"student": student, "total": total, "present": present,
                            "absent": absent, "leave": leave, "percentage": percentage})
    return render_template("reports.html", classes=classes, report_rows=report_rows,
                           start_date=start_date, end_date=end_date, class_filter=class_filter, q=q)


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="You do not have permission to access this page."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="The page or record could not be found."), 404


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
