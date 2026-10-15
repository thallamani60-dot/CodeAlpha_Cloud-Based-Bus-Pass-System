import base64, io, secrets, uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps
import qrcode
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, text
from config import Config
from .models import db, User, BusRoute, PassType, FareRule, PassApplication, BusPass, Payment, VerificationLog, Notification

csrf = CSRFProtect()
def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"): return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapped
def roles(*allowed):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get("role") not in allowed: abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return deco
def qr_data(token):
    image = qrcode.make(token); output = io.BytesIO(); image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()
def create_app(test_config=None):
    app = Flask(__name__); app.config.from_object(Config)
    if test_config: app.config.update(test_config)
    db.init_app(app); csrf.init_app(app)
    @app.context_processor
    def inject_user(): return {"current_user": db.session.get(User, session.get("user_id")) if session.get("user_id") else None}
    @app.get("/")
    def index(): return render_template("index.html", routes=BusRoute.query.filter_by(active=True).all())
    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name=request.form.get("name", "").strip(); email=request.form.get("email", "").strip().lower(); password=request.form.get("password", "")
            if not name or len(name)>120 or "@" not in email or len(password)<10:
                flash("Enter a name, valid email, and password of at least 10 characters.", "error")
            elif User.query.filter_by(email=email).first(): flash("That email is already registered.", "error")
            else:
                user=User(name=name,email=email,role="passenger"); user.set_password(password); db.session.add(user); db.session.commit(); flash("Account created. Please sign in.", "success"); return redirect(url_for("login"))
        return render_template("auth/register.html")
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            user=User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
            if user and user.check_password(request.form.get("password", "")):
                session.clear(); session["user_id"]=user.id; session["role"]=user.role; session.permanent=True
                return redirect(url_for("admin_dashboard" if user.role=="admin" else "verifier" if user.role=="verifier" else "dashboard"))
            flash("Email or password was not recognized.", "error")
        return render_template("auth/login.html")
    @app.post("/logout")
    @login_required
    def logout(): session.clear(); return redirect(url_for("index"))
    @app.get("/health")
    def health():
        try: db.session.execute(text("SELECT 1")); return {"status":"ok","database":"ok"},200
        except Exception: app.logger.exception("Health check database failure"); return {"status":"degraded"},503
    @app.get("/dashboard")
    @roles("passenger")
    def dashboard():
        uid=session["user_id"]; apps=PassApplication.query.filter_by(user_id=uid).order_by(PassApplication.created_at.desc()).all(); passes=BusPass.query.filter_by(user_id=uid).order_by(BusPass.expires_at.desc()).all(); payments=Payment.query.filter_by(user_id=uid).order_by(Payment.created_at.desc()).all()
        for p in passes:
            if p.status=="Active" and p.expires_at < date.today(): p.status="Expired"
        db.session.commit(); return render_template("passenger/dashboard.html",applications=apps,passes=passes,payments=payments)
    @app.route("/apply", methods=["GET","POST"])
    @roles("passenger")
    def apply():
        routes=BusRoute.query.filter_by(active=True).all(); types=PassType.query.filter_by(active=True).all()
        if request.method=="POST":
            try: route_id=int(request.form.get("route_id")); type_id=int(request.form.get("pass_type_id"))
            except (TypeError,ValueError): flash("Choose a route and pass type.","error"); return render_template("passenger/apply.html",routes=routes,types=types)
            rule=FareRule.query.filter_by(route_id=route_id,pass_type_id=type_id,active=True).first()
            if not rule: flash("That route and pass type is not currently available.","error")
            else:
                a=PassApplication(user_id=session["user_id"],route_id=route_id,pass_type_id=type_id); db.session.add(a); db.session.commit(); return redirect(url_for("payment",application_id=a.id))
        return render_template("passenger/apply.html",routes=routes,types=types)
    @app.route("/payment/<int:application_id>", methods=["GET","POST"])
    @roles("passenger")
    def payment(application_id):
        a=PassApplication.query.filter_by(id=application_id,user_id=session["user_id"]).first_or_404(); rule=FareRule.query.filter_by(route_id=a.route_id,pass_type_id=a.pass_type_id,active=True).first_or_404()
        if a.status == "Pending":
            return render_template("passenger/payment.html", application=a, fare=rule.amount, waiting=True)
        if a.status != "Approved": abort(400)
        prior=Payment.query.filter_by(application_id=a.id,status="Success").first()
        if prior: return redirect(url_for("my_pass",application_id=a.id))
        if request.method=="POST":
            # In demo the passenger chooses an outcome; no card details are collected.
            if Payment.query.filter_by(application_id=a.id).filter(Payment.status=="Success").first(): return redirect(url_for("my_pass",application_id=a.id))
            success=request.form.get("outcome")=="success"; pay=Payment(application_id=a.id,user_id=session["user_id"],transaction_ref="DEMO-"+uuid.uuid4().hex[:16].upper(),amount=rule.amount,status="Success" if success else "Failed"); db.session.add(pay)
            if success and a.status=="Approved":
                pt=db.session.get(PassType,a.pass_type_id); today=date.today(); bp=BusPass(application_id=a.id,user_id=a.user_id,route_id=a.route_id,pass_type_id=a.pass_type_id,pass_number="BP-"+uuid.uuid4().hex[:12].upper(),verification_token=secrets.token_urlsafe(24),issued_at=today,expires_at=today+timedelta(days=pt.duration_days)); db.session.add(bp); a.status="Active"; db.session.add(Notification(user_id=a.user_id,message="Your payment succeeded and your digital pass is active."))
            db.session.commit(); flash("Demo payment succeeded." if success else "Demo payment failed. No pass was activated.","success" if success else "error")
            if success and a.status=="Active": return redirect(url_for("my_pass",application_id=a.id))
        return render_template("passenger/payment.html",application=a,fare=rule.amount)
    @app.get("/pass/<int:application_id>")
    @roles("passenger")
    def my_pass(application_id):
        p=BusPass.query.filter_by(application_id=application_id,user_id=session["user_id"]).first_or_404()
        if p.status=="Active" and p.expires_at<date.today(): p.status="Expired"; db.session.commit()
        return render_template("passenger/pass.html",bus_pass=p,qr=qr_data(p.verification_token))
    @app.get("/admin")
    @roles("admin")
    def admin_dashboard():
        counts={"passengers":User.query.filter_by(role="passenger").count(),"active":BusPass.query.filter_by(status="Active").count(),"pending":PassApplication.query.filter_by(status="Pending").count(),"expired":BusPass.query.filter_by(status="Expired").count(),"revoked":BusPass.query.filter_by(status="Revoked").count(),"revenue":db.session.query(func.coalesce(func.sum(Payment.amount),0)).filter_by(status="Success").scalar()}
        apps=PassApplication.query.order_by(PassApplication.created_at.desc()).limit(50).all(); routes=BusRoute.query.order_by(BusRoute.code).all(); types=PassType.query.all(); rules=FareRule.query.all()
        return render_template("admin/dashboard.html",counts=counts,applications=apps,routes=routes,types=types,rules=rules)
    @app.post("/admin/application/<int:app_id>")
    @roles("admin")
    def review(app_id):
        a=db.get_or_404(PassApplication,app_id); action=request.form.get("action"); reason=request.form.get("reason","").strip()[:500]
        if a.status!="Pending" or action not in ("approve","reject"): abort(400)
        a.status="Approved" if action=="approve" else "Rejected"; a.review_reason=reason; a.reviewed_at=datetime.utcnow(); db.session.add(Notification(user_id=a.user_id,message=f"Application {a.status.lower()}. {reason}")); db.session.commit(); flash(f"Application {a.status.lower()}.","success"); return redirect(url_for("admin_dashboard"))
    @app.post("/admin/route")
    @roles("admin")
    def add_route():
        code=request.form.get("code","").strip().upper(); name=request.form.get("name","").strip(); origin=request.form.get("origin","").strip(); destination=request.form.get("destination","").strip()
        if not all([code,name,origin,destination]) or BusRoute.query.filter_by(code=code).first(): flash("Complete route fields and use a unique code.","error")
        else: db.session.add(BusRoute(code=code,name=name,origin=origin,destination=destination)); db.session.commit(); flash("Route added.","success")
        return redirect(url_for("admin_dashboard"))
    @app.post("/admin/fare")
    @roles("admin")
    def set_fare():
        try: rid=int(request.form["route_id"]); tid=int(request.form["pass_type_id"]); amount=Decimal(request.form["amount"])
        except Exception: flash("Enter a valid route, pass type, and amount.","error"); return redirect(url_for("admin_dashboard"))
        if amount<=0 or amount>Decimal("100000"): flash("Fare must be between 0 and 100000.","error")
        else:
            rule=FareRule.query.filter_by(route_id=rid,pass_type_id=tid).first()
            if rule: rule.amount=amount; rule.active=True
            else: db.session.add(FareRule(route_id=rid,pass_type_id=tid,amount=amount))
            db.session.commit(); flash("Fare saved.","success")
        return redirect(url_for("admin_dashboard"))
    @app.post("/admin/pass/<int:pass_id>/revoke")
    @roles("admin")
    def revoke(pass_id):
        p=db.get_or_404(BusPass,pass_id); p.status="Revoked"; db.session.commit(); flash("Pass revoked.","success"); return redirect(url_for("admin_dashboard"))
    @app.route("/verify",methods=["GET","POST"])
    @roles("verifier","admin")
    def verifier():
        result=None
        if request.method=="POST":
            token=request.form.get("token","").strip(); p=BusPass.query.filter_by(verification_token=token).first()
            state="Invalid" if not p else "Revoked" if p.status=="Revoked" else "Expired" if p.expires_at<date.today() or p.status=="Expired" else "Valid" if p.status=="Active" else "Invalid"
            if p and state=="Expired": p.status="Expired"
            db.session.add(VerificationLog(pass_id=p.id if p else None,verifier_id=session["user_id"],result=state)); db.session.commit()
            result={"status":state,"pass_number":p.pass_number if p else None,"route":p.route.name if p else None,"expiry":p.expires_at if p else None}
        return render_template("verifier/index.html",result=result)
    @app.cli.command("init-db")
    def init_db():
        """Create schema and a small starter catalogue."""
        db.create_all()
        if not BusRoute.query.first():
            r=BusRoute(code="R-01",name="Central Connector",origin="Central Station",destination="University Campus"); db.session.add(r)
            for category in ("student","general","employee"):
                for duration,days in (("monthly",30),("quarterly",90)):
                    p=PassType(category=category,duration=duration,duration_days=days); db.session.add(p); db.session.flush(); db.session.add(FareRule(route=r,pass_type=p,amount=Decimal("450" if duration=="monthly" else "1200")))
            db.session.commit()
        print("Database ready. Create users with flask create-user.")
    @app.cli.command("create-user")
    def create_user():
        """Create an admin, verifier, or passenger without hardcoded passwords."""
        import click
        email=click.prompt("Email").strip().lower(); name=click.prompt("Name"); role=click.prompt("Role",type=click.Choice(["admin","verifier","passenger"])); password=click.prompt("Password",hide_input=True,confirmation_prompt=True)
        if len(password)<10: raise click.ClickException("Password must contain at least 10 characters.")
        if User.query.filter_by(email=email).first(): raise click.ClickException("Email already exists.")
        user=User(name=name,email=email,role=role); user.set_password(password); db.session.add(user); db.session.commit(); print(f"Created {role} account: {email}")
    @app.errorhandler(403)
    def forbidden(_): return render_template("error.html",code=403,message="You do not have access to this page."),403
    @app.errorhandler(404)
    def not_found(_): return render_template("error.html",code=404,message="We could not find that page."),404
    @app.errorhandler(500)
    def server_error(_): db.session.rollback(); app.logger.exception("Unhandled application error"); return render_template("error.html",code=500,message="Something went wrong. Please try again."),500
    return app


