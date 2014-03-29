# -*- coding: utf-8 -*-

# Copyright (C) 2013-2014 Piotr Żurek <piotr at sology.eu> for Sology

# This file contains Redmine Integration specific functions for Project Hamster

# Project Hamster is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Project Hamster is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Project Hamster.  If not, see <http://www.gnu.org/licenses/>.

import httplib
import json
import datetime
import urlparse

class RedmineConnectionException(Exception):
  def __init__(self, value):
    self.value=value
  def __str__(self):
    return repr(self.value)
    
class RedmineActionException(Exception):
  def __init__(self, value):
    self.value=value
  def __str__(self):
    return repr(self.value)

class RedmineConnector:
  
  def __init__(self, url, key):
    parsed = urlparse.urlparse(url)
    self.server = parsed.hostname
    self.path = parsed.path
    self.scheme = parsed.scheme
    if self.path == "":
      self.path = "/"
    self.port = parsed.port
    if self.port == None:
      if self.scheme == "https":
        self.port = 443
      else:
        self.port = 80
    self.apikey = key
  
  def get_current_user_id(self):
    if self.scheme == "https":
      conn = httplib.HTTPSConnection(self.server, self.port, timeout=10)
    else:
      conn = httplib.HTTPConnection(self.server, self.port, timeout=10)
    conn.putrequest("GET", self.path + "users/current.json")
    conn.putheader("X-Redmine-API-Key", self.apikey)
    conn.endheaders()
    conn.send("")
    resp = conn.getresponse()
    if resp.status == 200:
      userdata = json.load(resp)
      conn.close()
      return userdata['user']['id']
    else:
      raise RedmineConnectionException("HTTP replied: " + str(resp.status) + " " + resp.reason)
      
  def check_connection(self):
    try:
      self.get_current_user_id()
      return True
    except RedmineConnectionException as e:
      return False
      
  def get_issues(self):
    userid = self.get_current_user_id()
    if self.scheme == "https":
      conn = httplib.HTTPSConnection(self.server, self.port, timeout=10)
    else:
      conn = httplib.HTTPConnection(self.server, self.port, timeout=10)
    conn.putrequest("GET", self.path + "issues.json?assigned_to_id=" + str(userid))
    conn.putheader("X-Redmine-API-Key", self.apikey)
    conn.endheaders()
    conn.send("")
    resp = conn.getresponse()
    if resp.status == 200:
      issuelist = json.load(resp)
      conn.close()
      return issuelist
    else:
      raise RedmineConnectionException("HTTP replied: " + str(resp.status) + " " + resp.reason)
      
  def get_arbitrary_issue_data(self, issue):
    if self.scheme == "https":
      conn = httplib.HTTPSConnection(self.server, self.port, timeout=10)
    else:
      conn = httplib.HTTPConnection(self.server, self.port, timeout=10)
    conn.putrequest("GET", self.path + "issues/" + str(issue) + ".json")
    conn.putheader("X-Redmine-API-Key", self.apikey)
    conn.endheaders()
    conn.send("")
    resp = conn.getresponse()
    if resp.status == 200:
      issuedata = json.load(resp)
      conn.close()
      return issuedata
    else:
      raise RedmineConnectionException("HTTP replied: " + str(resp.status) + " " + resp.reason)

  def add_time_entry(self, issue, hours, activity, comments):
    timeentryhash = {'time_entry' : {'issue_id' : issue, 'hours' : hours, 'activity_id' : activity, 'comments' : comments, 'spent_on' : datetime.date.today().strftime('%Y-%m-%d')}}
    timeentryjson = json.dumps(timeentryhash)
    if self.scheme == "https":
      conn = httplib.HTTPSConnection(self.server, self.port, timeout=10)
    else:
      conn = httplib.HTTPConnection(self.server, self.port, timeout=10)
    conn.putrequest("POST", self.path + "time_entries.json")
    conn.putheader("X-Redmine-API-Key", self.apikey)
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", len(timeentryjson))
    conn.endheaders()
    conn.send(timeentryjson)
    resp = conn.getresponse()
    if resp.status == 201:
      conn.close()
      return True
    elif resp.status == 422:
      raise RedmineActionException("Error while adding the time entry: Unprocessable Entity: " + resp.read())
    else:
      raise RedmineConnectionException("HTTP replied: " + str(resp.status) + " " + resp.reason)
       
  def get_activities(self):
    userid = self.get_current_user_id()
    if self.scheme == "https":
      conn = httplib.HTTPSConnection(self.server, self.port, timeout=10)
    else:
      conn = httplib.HTTPConnection(self.server, self.port, timeout=10)
    conn.putrequest("GET", self.path + "enumerations/time_entry_activities.json")
    conn.putheader("X-Redmine-API-Key", self.apikey)
    conn.endheaders()
    conn.send("")
    resp = conn.getresponse()
    if resp.status == 200:
      activitylist = json.load(resp)
      conn.close()
      return activitylist
    else:
      raise RedmineConnectionException("HTTP replied: " + str(resp.status) + " " + resp.reason)
      
  def get_redmine_activity_id(self, name):
    activities = self.get_activities()
    for activity in activities['time_entry_activities']:
      if activity['name'] == name:
        return activity['id']
    return None
    
  def get_redmine_issue_id(self, subject):
    issues = self.get_issues()
    for issue in issues['issues']:
      if issue['subject'] == subject:
        return issue['id']
    return None
