#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os, re, datetime
from bson.objectid import ObjectId
# import bcrypt - fuck this shit, seriously hate this library
from flask import current_app, Flask, Blueprint, request, session, g, redirect, url_for, \
    abort, render_template, flash
from contextlib import closing
from flask.ext.pymongo import PyMongo
from jinja2 import TemplateNotFound
from evarist.models import model_user
from evarist.forms import SignUpForm, SignInForm


from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
from oauth2client.client import AccessTokenCredentials
import httplib2, json, uuid, hashlib, string, random
from flask import make_response
import requests

# def json_to_obj(s):
#     def h2o(x):
#         if isinstance(x, dict):
#             return type('jo', (), {k: h2o(v) for k, v in x.iteritems()})
#         else:
#             return x
#     return h2o(json.loads(s))





user = Blueprint('user', __name__,
                        template_folder='templates')


@user.route('/user/signup', methods=['GET', 'POST'])
def signup():
    # for i in g.db.users.find():
    #     print i

    if "username" in session:
        flash('please log out first')
        return redirect(url_for('workflow.home'))

    signup_form=SignUpForm()

    if request.method == 'POST' and signup_form.validate_on_submit():
        if signup_form.password.data == signup_form.confirm_password.data:
            model_user.add(email=signup_form.email.data,
                            picture='https://cdn.rawgit.com/artofkot/evarist_static/master/no_pic.jpg',
                            password=signup_form.password.data,
                            username=signup_form.username.data,
                            db=g.db,
                            secret_key=current_app.config["SECRET_KEY"])
            return redirect(url_for('user.login'))
        else:
            flash('passwords should be the same, try one more time, please')
            return redirect(url_for('user.signup'))
        

    error=''
    if request.method == 'POST' and not signup_form.validate_on_submit():
        for err in signup_form.errors:
            error=error+signup_form.errors[err][0]+' '
        return render_template("user/signup.html", error=error, signup_form=SignUpForm())

    return render_template("user/signup.html", error=error, signup_form=signup_form)

@user.route('/user/login', methods=['GET', 'POST'])
def login():
    if "email" in session:
        flash('please log out first')
        return redirect(url_for('workflow.home'))

    state=''.join(random.choice(string.ascii_uppercase + string.digits) for x in xrange(32))
    session['state']=state

    error = ''

    signin_form=SignInForm()

    if request.method == 'POST' and signin_form.validate_on_submit():

        email=signin_form.email.data
        password=signin_form.password.data

        user=g.db.users.find_one({"email": email})
        if user:
            print user
            if model_user.check_pwd(password,user["pw_hash"],secret_key=current_app.config["SECRET_KEY"]):
                session['username'] = user['username']
                session['picture'] = user['picture']
                session['email']=user['email']
                session['is_moderator']=user['rights']['is_moderator']
                session['is_checker']=user['rights']['is_checker']


                return redirect(url_for('workflow.home'))
            else:
                error = 'Invalid password'
        else:
            error = 'Invalid username'

    if request.method == 'POST' and not signin_form.validate_on_submit():
        for err in signin_form.errors:
            error=error+signin_form.errors[err][0]+' '
        return render_template("user/login.html", error=error, signin_form=SignInForm())
    print current_app.config['CLIENT_ID']
    return render_template('user/login.html', error=error, signin_form=signin_form, client_id_yep=current_app.config['CLIENT_ID']) #fb_app_id_yep=current_app.config['FB_APP_ID'])

@user.route('/user/gconnect', methods=['POST'])
def gconnect():


    # Validate state token
    if request.args.get('state') != session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object

        # CLIENT_SECRETS_JSON = json.loads(os.environ.get("CLIENT_SECRETS_JSON"))
        temp_file = open("client_secrets.json", "w")
        temp_file.write(os.environ.get("CLIENT_SECRETS_JSON"))
        temp_file.close()
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        os.remove('client_secrets.json')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response



    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'



    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != current_app.config['CLIENT_ID']:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    # check if user is already connected
    stored_credentials = session.get('credentials')
    stored_gplus_id = session.get('gplus_id')
    if stored_credentials is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response


    # Store the access token in the session for later use.
    session['access_token'] = credentials.access_token
    session['gplus_id'] = gplus_id
    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)
    data = answer.json()
    session['provider'] = 'gplus'
    session['username'] = data['name']
    session['picture'] = data['picture']
    session['email'] = data['email']

    # add user if such email does not exist in database
    user_wasnt_in_db = model_user.add(email=session['email'],
                                    picture=session['picture'],
                                    password=current_app.config["SECRET_KEY"], #чтобы пользователи не могли зайти по паролю, только через гугл
                                    username=session['username'],
                                    db=g.db,
                                    secret_key=current_app.config["SECRET_KEY"])
    if user_wasnt_in_db:
        session['is_moderator']=False
        session['is_checker']=False
    else:
        user=g.db.users.find_one({"email": session['email']})
        session['is_moderator']=user['rights']['is_moderator']
        session['is_checker']=user['rights']['is_checker']
    

    output = ''
    output += '<h1>Welcome, '
    output += session['username']
    output += '!</h1>'
    output += '<img src="'
    output += session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % session['username'])
    print "done!"
    return output

# add this for pages where you want users to be logged in
# if 'username' not in session:
#     return redirect('/user/login')


@user.route('/user/gdisconnect')
def gdisconnect():
        # Only disconnect a connected user.
    access_token = session['access_token']
    if access_token is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]

    if result['status'] == '200':
        # Reset the user's sesson.
        del session['provider']
        del session['access_token']
        del session['gplus_id']
        del session['username']
        del session['email']
        del session['picture']
        session.pop('is_moderator', None)
        session.pop('is_checker', None)

        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return redirect(url_for('workflow.home'))
        # return response
    else:
        # For whatever reason, the given token was invalid.
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response

@user.route('/user/logout')
def logout():
    if session.get('provider')=='gplus':
        return redirect(url_for('user.gdisconnect'))
    else:
        session.pop('username', None)
        session.pop('provider', None)
        session.pop('is_moderator', None)
        session.pop('email', None)
        session.pop('picture', None)
        session.pop('is_checker', None)
        # We use a neat trick here:
        # if you use the pop() method of the dict and pass a second parameter to it (the default),
        # the method will delete the key from the dictionary if present or
        # do nothing when that key is not in there.
        return redirect(url_for('workflow.home'))

# @user.route('/fbconnect', methods=['POST'])
# def fbconnect():
#     if request.args.get('state') != session['state']:
#         response = make_response(json.dumps('Invalid state parameter.'), 401)
#         response.headers['Content-Type'] = 'application/json'
#         return response
#     access_token = request.data
#     print "access token received %s " % access_token

#     app_id = current_app.config['FB_CLIENTS_SECRETS_JSON'][
#         'web']['app_id']
#     app_secret = current_app.config['FB_CLIENTS_SECRETS_JSON']['web']['app_secret']
#     url = 'https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=%s&client_secret=%s&fb_exchange_token=%s' % (
#         app_id, app_secret, access_token)
#     h = httplib2.Http()
#     result = h.request(url, 'GET')[1]

#     # Use token to get user info from API
#     userinfo_url = "https://graph.facebook.com/v2.2/me"
#     # strip expire tag from access token
#     token = result.split("&")[0]


#     url = 'https://graph.facebook.com/v2.2/me?%s' % token
#     h = httplib2.Http()
#     result = h.request(url, 'GET')[1]
#     # print "url sent for API access:%s"% url
#     # print "API JSON result: %s" % result
#     data = json.loads(result)
#     session['provider'] = 'facebook'
#     session['username'] = data["name"]
#     session['email'] = data["email"]
#     session['facebook_id'] = data["id"]

#     # The token must be stored in the session in order to properly logout, let's strip out the information before the equals sign in our token
#     stored_token = token.split("=")[1]
#     session['access_token'] = stored_token

#     # Get user picture
#     url = 'https://graph.facebook.com/v2.2/me/picture?%s&redirect=0&height=200&width=200' % token
#     h = httplib2.Http()
#     result = h.request(url, 'GET')[1]
#     data = json.loads(result)

#     session['picture'] = data["data"]["url"]

#     # see if user exists
#     user_id = getUserID(session['email'])
#     if not user_id:
#         user_id = createUser(session)
#     session['user_id'] = user_id

#     output = ''
#     output += '<h1>Welcome, '
#     output += session['username']

#     output += '!</h1>'
#     output += '<img src="'
#     output += session['picture']
#     output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '

#     flash("Now logged in as %s" % session['username'])
#     return output


# @user.route('/fbdisconnect')
# def fbdisconnect():
#     facebook_id = session['facebook_id']
#     # The access token must me included to successfully logout
#     access_token = session['access_token']
#     url = 'https://graph.facebook.com/%s/permissions' % (facebook_id,access_token)
#     h = httplib2.Http()
#     result = h.request(url, 'DELETE')[1]
#     return "you have been logged out"
