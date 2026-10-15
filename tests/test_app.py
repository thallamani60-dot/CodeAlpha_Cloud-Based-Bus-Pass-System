import pytest
from app import create_app
from app.models import db, User, BusRoute, PassType, FareRule, PassApplication, BusPass

@pytest.fixture()
def client():
    app=create_app({"TESTING":True,"WTF_CSRF_ENABLED":False,"SQLALCHEMY_DATABASE_URI":"sqlite://","SECRET_KEY":"test"})
    with app.app_context():
        db.create_all()
        user=User(name="Test Passenger",email="p@example.test",role="passenger"); user.set_password("password12345")
        admin=User(name="Admin",email="a@example.test",role="admin"); admin.set_password("password12345")
        verifier=User(name="Verifier",email="v@example.test",role="verifier"); verifier.set_password("password12345")
        route=BusRoute(code="T1",name="Test Route",origin="A",destination="B"); kind=PassType(category="student",duration="monthly",duration_days=30)
        db.session.add_all([user,admin,verifier,route,kind]); db.session.flush(); db.session.add(FareRule(route_id=route.id,pass_type_id=kind.id,amount=450)); db.session.commit()
        yield app.test_client()
        db.session.remove(); db.drop_all()

def login(client,email):
    return client.post('/login',data={"email":email,"password":"password12345"},follow_redirects=True)

def test_health(client):
    response=client.get('/health'); assert response.status_code==200 and response.json["status"]=="ok"

def test_registration_and_logout(client):
    response=client.post('/register',data={"name":"New User","email":"new@example.test","password":"securepassword1"},follow_redirects=True)
    assert response.status_code==200 and b"Account created" in response.data
    login(client,"new@example.test"); assert client.post('/logout').status_code==302

def test_role_protection(client):
    assert client.get('/admin').status_code==302
    login(client,"p@example.test"); assert client.get('/admin').status_code==403

def test_approval_payment_and_pass(client):
    login(client,"p@example.test")
    with client.session_transaction() as sess: pass
    # get seeded IDs and use them without trusting a browser-provided fare
    response=client.post('/apply',data={"route_id":1,"pass_type_id":1},follow_redirects=False); assert response.status_code==302
    with client.application.app_context():
        a=PassApplication.query.first(); aid=a.id
    # Pending applications cannot be paid until reviewed.
    login(client,"a@example.test")
    client.post(f'/admin/application/{aid}',data={"action":"approve","reason":""})
    login(client,"p@example.test")
    page=client.get(f'/payment/{aid}'); assert b"450" in page.data
    client.post(f'/payment/{aid}',data={"outcome":"success"})
    with client.application.app_context():
        assert PassApplication.query.get(aid).status=="Active"
        assert BusPass.query.filter_by(application_id=aid).count()==1
    assert client.get(f'/pass/{aid}').status_code==200
