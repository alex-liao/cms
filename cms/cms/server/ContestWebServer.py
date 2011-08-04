#!/usr/bin/python
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2010-2011 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2011 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2011 Matteo Boscariol <boscarim@hotmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.escape

import os
import pickle
import sys
import tempfile
import zipfile
import threading
import time

import BusinessLayer
import cms.util.Configuration as Configuration
import cms.util.WebConfig as WebConfig
import cms.util.Utils as Utils
from cms.db.SQLAlchemyAll import Submission


class BaseHandler(tornado.web.RequestHandler):
    """Base RequestHandler for this application.

    All the RequestHandler classes in this application should be a
    child of this class.
    """

    def prepare(self):
        """This method is executed at the beginning of each request.
        """
        # Attempt to update the contest and all its references
        # If this fails, the request terminates.
        self.set_header("Cache-Control", "no-cache, must-revalidate")
        try:
            c.refresh()
        except Exception as e:
            Utils.log("CouchDB exception:" + repr(e),
                      Utils.Logger.SEVERITY_CRITICAL)
            self.write("Can't connect to CouchDB Server")
            self.finish()

    def get_current_user(self):
        """Gets the current user logged in from the cookies

        If a valid cookie is retrieved, returns a User object with the
        username specified in the cookie. Otherwise, returns None.
        """
        if self.get_secure_cookie("login") == None:
            return None
        try:
            username, cookie_time = \
                pickle.loads(self.get_secure_cookie("login"))
        except:
            self.clear_cookie("login")
            return None
        #if cookie_time == None or cookie_time < upsince:
        #    return None
        current_user = BusinessLayer.get_user_by_username(c, username)
        if current_user == None:
            self.clear_cookie("login")
            return None
        current_user.refresh()
        return current_user

    def render_params(self):
        """Default parameters to give to all handlers
        """
        r = {}
        r["timestamp"] = time.time()
        r["contest"] = c
        r["phase"] = BusinessLayer.contest_phase(**r)
        r["cookie"] = str(self.cookies)
        return r

    def valid_phase(self, r_param):
        if r_param["phase"] != 0:
            self.redirect("/")
            return False
        return True


class MainHandler(BaseHandler):
    """Home page handler.
    """

    def get(self):
        r_params = self.render_params()
        self.render("welcome.html", **r_params)


class LoginHandler(BaseHandler):
    """Login handler.
    """

    def post(self):
        username = self.get_argument("username", "")
        password = self.get_argument("password", "")
        next = self.get_argument("next", "/")
        user = BusinessLayer.get_user_by_username(c, username)
        if user != None:
          user.refresh()
        if user == None or user.password != password:
            Utils.log("Login error: user=%s pass=%s remote_ip=%s." %
                      (username, password, self.request.remote_ip))
            self.redirect("/?login_error=true")
            return
        if WebConfig.ip_lock and user.ip != "0.0.0.0" \
                and user.ip != self.request.remote_ip:
            Utils.log("Unexpected IP: user=%s pass=%s remote_ip=%s." %
                      (username, password, self.request.remote_ip))
            self.redirect("/?login_error=true")
            return
        if user.hidden and WebConfig.block_hidden_users:
            Utils.log("Hidden user login attempt: " +
                      "user=%s pass=%s remote_ip=%s." %
                      (username, password, self.request.remote_ip))
            self.redirect("/?login_error=true")
            return

        self.set_secure_cookie("login",
                               pickle.dumps((self.get_argument("username"),
                                             time.time())))
        self.redirect(next)


class LogoutHandler(BaseHandler):
    """Logout handler.
    """

    def get(self):
        self.clear_cookie("login")
        self.redirect("/")


class SubmissionViewHandler(BaseHandler):
    """Shows the submissions stored in the contest.
    """

    @tornado.web.authenticated
    def get(self, task_name):

        r_params = self.render_params()
        if not self.valid_phase(r_params):
            return
        # get the task object
        try:
            r_params["task"] = c.get_task(task_name)
        except:
            self.write("Task %s not found." % (task_name))
            return

        r_params["task"].refresh()

        # get the list of the submissions
        r_params["submissions"] = BusinessLayer.get_submissions_by_username(\
                c, self.current_user.username, task_name)
        BusinessLayer.refresh_array(r_params["submissions"])

        self.render("submission.html", **r_params)


class SubmissionDetailHandler(BaseHandler):
    """Shows additional details for the specified submission.
    """

    @tornado.web.authenticated
    def get(self, submission_id):

        r_params = self.render_params()
        if not self.valid_phase(r_params):
            return
        # search the submission in the contest
        submission = BusinessLayer.get_submission(c,
                                                  submission_id,
                                                  self.current_user.username)
        if submission == None:
            raise tornado.web.HTTPError(404)
        submission.refresh()
        r_params["submission"] = submission
        r_params["task"] = submission.task
        r_params["task"].refresh()
        self.render("submission_detail.html", **r_params)


class SubmissionFileHandler(BaseHandler):
    """Shows a submission file.
    """

    @tornado.web.authenticated
    def get(self, submission_id, filename):

        r_params = self.render_params()
        if not self.valid_phase(r_params):
            return
        submission = BusinessLayer.get_submission(c,
                                                  submission_id,
                                                  self.current_user.username)
        submission.refresh()
        # search the submission in the contest
        file_content = BusinessLayer.get_file_from_submission(submission,
                                                              filename)
        if file_content == None:
            raise tornado.web.HTTPError(404)

        # FIXME - Set the right headers
        self.set_header("Content-Type", "text/plain")
        self.set_header("Content-Disposition",
                        "attachment; filename=\"%s\"" % (filename))
        self.write(file_content)


class TaskViewHandler(BaseHandler):
    """Shows the data of a task in the contest.
    """

    @tornado.web.authenticated
    def get(self, task_name):

        r_params = self.render_params()
        if not self.valid_phase(r_params):
            return
        try:
            r_params["task"] = c.get_task(task_name)
        except:
            raise tornado.web.HTTPError(404)
        r_params["task"].refresh()
        r_params["submissions"] = BusinessLayer.get_submissions_by_username(\
            c, self.current_user.username, task_name)
        BusinessLayer.refresh_array(r_params["submissions"])

        self.render("task.html", **r_params)


class TaskStatementViewHandler(BaseHandler):
    """Shows the statement file of a task in the contest.
    """

    @tornado.web.authenticated
    def get(self, task_name):

        r_params = self.render_params()
        if not self.valid_phase(r_params):
            return
        try:
            task = c.get_task(task_name)
        except:
            self.write("Task %s not found." % (task_name))
        task.refresh()

        statement = BusinessLayer.get_task_statement(task)

        if statement == None:
            raise tornado.web.HTTPError(404)

        self.set_header("Content-Type", "application/pdf")
        self.set_header("Content-Disposition",
                        "attachment; filename=\"%s.pdf\"" % (task.name))
        self.write(statement)


class UseTokenHandler(BaseHandler):
    """Handles the detailed feedbaack requests.
    """

    @tornado.web.authenticated
    def post(self):
        r_params = self.render_params()
        if not self.valid_phase(r_params):
            return
        timestamp = r_params["timestamp"]

        sub_id = self.get_argument("id", "")
        if sub_id == "":
            raise tornado.web.HTTPError(404)

        s = BusinessLayer.get_submission(c, sub_id, self.current_user.username)
        if s == None:
            raise tornado.web.HTTPError(404)
        s.refresh()

        try:
            warned = BusinessLayer.enable_detailed_feedback(c, s, timestamp,
                                                            self.current_user)
            r_params["submission"] = s
            self.render("successfulToken.html", **r_params)
        except BusinessLayer.FeedbackAlreadyRequested:
            # Either warn the user about the issue or simply
            # redirect him to the detail page.
            self.redirect("/submissions/details/" + sub_id)
            return
        except BusinessLayer.TokenUnavailableException:
            # Redirect the user to the detail page
            # warning him about the unavailable tokens.
            self.redirect("/submissions/details/" + sub_id + "?notokens=true")
            return
        except BusinessLayer.ConnectionFailure:
            self.render("errors/connectionFailure.html")
        except couchdb.ResourceConflict:
            self.render("errors/conflictError.html")
            return


class SubmitHandler(BaseHandler):
    """Handles the received submissions.
    """

    @tornado.web.authenticated
    def post(self, task_name):

        r_params = self.render_params()
        if not self.valid_phase(r_params):
            return
        timestamp = r_params["timestamp"]

        task = c.get_task(task_name)
        task.refresh()

        try:
            uploaded = self.request.files[task_name][0]
        except KeyError:
            self.write("No file chosen.")
            return
        files = {}

        if uploaded["content_type"] == "application/zip":
            #Extract the files from the archive
            temp_zip_file, temp_zip_filename = tempfile.mkstemp()
            # Note: this is just a binary copy, so no utf-8 wtf-ery here.
            with os.fdopen(temp_zip_file, "w") as temp_zip_file:
                temp_zip_file.write(uploaded["body"])

            zip_object = zipfile.ZipFile(temp_zip_filename, "r")
            for item in zip_object.infolist():
                files[item.filename] = zip_object.read(item)
        else:
            files[uploaded["filename"]] = uploaded["body"]

        try:
            s, warned = BusinessLayer.submit(c, task, self.current_user,
                                             files, timestamp)
            r_params["submission"] = s
            r_params["warned"] = warned
            self.render("successfulSub.html", **r_params)
        except couchdb.ResourceConflict:
            self.render("errors/conflictError.html", **r_params)
        except BusinessLayer.ConnectionFailure:
            self.render("errors/connectionFailure.html", **r_params)
        except BusinessLayer.StorageFailure:
            self.render("errors/storageFailure.html", **r_params)
        except BusinessLayer.InvalidSubmission:
            self.render("errors/invalidSubmission.html", **r_params)
        except BusinessLayer.RepeatedSubmission:
            self.redirect("/tasks/%s?repeated=true" % task.name)


class UserHandler(BaseHandler):

    @tornado.web.authenticated
    def get(self):
        r_params = self.render_params()
        self.render("user.html", **r_params)


class InstructionHandler(BaseHandler):

    def get(self):
        r_params = self.render_params()
        self.render("instructions.html", **r_params)


class NotificationsHandler(BaseHandler):

    def post(self):
        timestamp = time.time()
        last_request = self.get_argument("lastrequest", timestamp)
        messages = []
        announcements = []
        if last_request != "":
            announcements = [x for x in c.announcements
                             if x["date"] > float(last_request) \
                                 and x["date"] < timestamp]
            if self.current_user != None:
                messages = [x for x in self.current_user.messages
                            if x["date"] > float(last_request) \
                                and x["date"] < timestamp]
        self.set_header("Content-Type", "text/xml")
        self.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
        self.write("<root>")
        for ann_item in announcements:
            self.write("<announcement>%s</announcement>" % ann_item["subject"])
        for mess_item in messages:
            self.write("<message>%s</message>" % mess_item["subject"])
        self.write("<requestdate>%s</requestdate>" % str(timestamp))
        self.write("</root>")


class QuestionHandler(BaseHandler):

    @tornado.web.authenticated
    def post(self):
        print self.request
        r_params = self.render_params()
        question_subject = self.get_argument("question_subject","")

        question_text = self.get_argument("question_text","")
        BusinessLayer.add_user_question(self.current_user,time.time(),\
                question_subject, question_text)
        Utils.log("Question submitted by user %s."
                  % self.current_user.username,
                  Utils.logger.SEVERITY_NORMAL)
        self.render("successfulQuestion.html", **r_params)

handlers = [
            (r"/", \
                 MainHandler),
            (r"/login", \
                 LoginHandler),
            (r"/logout", \
                 LogoutHandler),
            (r"/submissions/([a-zA-Z0-9_-]+)", \
                 SubmissionViewHandler),
            (r"/submissions/details/([a-zA-Z0-9_-]+)", \
                 SubmissionDetailHandler),
            (r"/submission_file/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)", \
                 SubmissionFileHandler),
            (r"/tasks/([a-zA-Z0-9_-]+)", \
                 TaskViewHandler),
            (r"/tasks/([a-zA-Z0-9_-]+)/statement", \
                 TaskStatementViewHandler),
            (r"/usetoken/", \
                 UseTokenHandler),
            (r"/submit/([a-zA-Z0-9_.-]+)", \
                 SubmitHandler),
            (r"/user", \
                 UserHandler),
            (r"/instructions", \
                 InstructionHandler),
            (r"/notifications", \
                 NotificationsHandler),
            (r"/question", \
                 QuestionHandler),
            (r"/stl/(.*)", \
                 tornado.web.StaticFileHandler, {"path": WebConfig.stl_path}),
           ]

application = tornado.web.Application(handlers, **WebConfig.contest_parameters)

if __name__ == "__main__":
    Utils.set_service("contest web server")
    http_server = tornado.httpserver.HTTPServer(\
        application, ssl_options=WebConfig.ssl_options)
    http_server.listen(WebConfig.contest_listen_port)
    try:
        c = Utils.ask_for_contest()
    except AttributeError as e:
        Utils.log("CouchDB server unavailable: " + repr(e),
                  Utils.Logger.SEVERITY_CRITICAL)
        exit(1)
    Utils.log("Contest Web Server for contest %s started..." % (c.couch_id))
    upsince = time.time()
    try:
        tornado.ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        Utils.log("Contest Web Server for contest " +
                  "%s stopped. %d threads alive" \
                      % (c.couch_id, threading.activeCount()))
        exit(0)