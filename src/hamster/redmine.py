# -*- coding: utf-8 -*-

# Copyright (C) 2013 Piotr Żurek <piotr at sology dot eu> for Sology

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
    if self.path == "":
      self.path = "/"
    self.port = parsed.port
    if self.port == None:
      self.port = 80
    self.apikey = key
  
  def get_current_user_id(self):
    conn = httplib.HTTPConnection(self.server, self.port)
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
    conn = httplib.HTTPConnection(self.server, self.port)
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
      
  def add_time_entry(self, issue, hours, activity, comments):
    timeentryhash = {'time_entry' : {'issue_id' : issue, 'hours' : hours, 'activity_id' : activity, 'comments' : comments, 'spent_on' : datetime.date.today().strftime('%Y-%m-%d')}}
    timeentryjson = json.dumps(timeentryhash)
    conn = httplib.HTTPConnection(self.server, self.port)
    conn.putrequest("POST", self.path + "time_entries.json")
    conn.putheader("X-Redmine-API-Key", self.apikey)
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", len(timeentryjson))
    conn.endheaders()
    print "Sending: " + timeentryjson
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
    conn = httplib.HTTPConnection(self.server, self.port)
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
