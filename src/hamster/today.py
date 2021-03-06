#!/usr/bin/env python
# - coding: utf-8 -

# Copyright (C) 2009-2012 Toms Bauģis <toms.baugis at gmail.com>
# Copyright (C) 2009 Patryk Zawadzki <patrys at pld-linux.org>
# Copyright (C) 2013-2014 Piotr Żurek <piotr at sology.eu> for Sology (Redmine Integration)

# This file is part of Project Hamster.

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
from __future__ import division # BEHOLD PYTHON3 DIVISION! int / int -> float
import sys
import logging
import datetime as dt

import gtk, gobject
import glib
import dbus, dbus.service, dbus.mainloop.glib
import locale
import redmine


from hamster.configuration import runtime, dialogs, conf, load_ui_file
from hamster import widgets
from hamster.lib import Fact, RedmineFact, trophies, stuff

try:
    import wnck
except:
    logging.warning("Could not import wnck - workspace tracking will be disabled")
    wnck = None


class ProjectHamsterStatusIcon(gtk.StatusIcon):
    def __init__(self, project):
        gtk.StatusIcon.__init__(self)

        self.project = project

        menu = '''
            <ui>
             <menubar name="Menubar">
              <menu action="Menu">
               <separator/>
               <menuitem action="Quit"/>
              </menu>
             </menubar>
            </ui>
        '''
        actions = [
            ('Menu',  None, 'Menu'),
            ('Quit', gtk.STOCK_QUIT, '_Quit...', None, 'Quit Time Tracker', self.on_quit)]
        ag = gtk.ActionGroup('Actions')
        ag.add_actions(actions)
        self.manager = gtk.UIManager()
        self.manager.insert_action_group(ag, 0)
        self.manager.add_ui_from_string(menu)
        self.menu = self.manager.get_widget('/Menubar/Menu/Quit').props.parent

        self.set_from_icon_name("hamster-time-tracker")
        self.set_name(_('Time Tracker'))

        self.connect('activate', self.on_activate)
        self.connect('popup-menu', self.on_popup_menu)

    def on_activate(self, data):
        self.project.toggle_hamster_window()

    def on_popup_menu(self, status, button, time):
        self.menu.popup(None, None, None, button, time)

    def on_quit(self, data):
        gtk.main_quit()



class DailyView(object):
    def __init__(self):
        # initialize the window.  explicitly set it to None first, so that the
        # creator knows it doesn't yet exist.
        self.window = None
        self.create_hamster_window()

        self.new_name.grab_focus()

        # configuration
        self.workspace_tracking = conf.get("workspace_tracking")

        conf.connect('conf-changed', self.on_conf_changed)

        # Load today's data, activities and set label
        self.last_activity = None
        self.todays_facts = None

        runtime.storage.connect('activities-changed',self.after_activity_update)
        runtime.storage.connect('facts-changed',self.after_fact_update)
        runtime.storage.connect('toggle-called', self.on_toggle_called)

        self.screen = None
        if self.workspace_tracking:
            self.init_workspace_tracking()


        # refresh hamster every 60 seconds
        gobject.timeout_add_seconds(60, self.refresh_hamster)

        self.prev_size = None

        # bindings
        self.accel_group = self.get_widget("accelgroup")
        self.window.add_accel_group(self.accel_group)

        gtk.accel_map_add_entry("<hamster-time-tracker>/tracking/add", gtk.keysyms.n, gtk.gdk.CONTROL_MASK)
        gtk.accel_map_add_entry("<hamster-time-tracker>/tracking/overview", gtk.keysyms.o, gtk.gdk.CONTROL_MASK)
        gtk.accel_map_add_entry("<hamster-time-tracker>/tracking/stats", gtk.keysyms.i, gtk.gdk.CONTROL_MASK)
        gtk.accel_map_add_entry("<hamster-time-tracker>/tracking/close", gtk.keysyms.Escape, 0)
        gtk.accel_map_add_entry("<hamster-time-tracker>/tracking/quit", gtk.keysyms.q, gtk.gdk.CONTROL_MASK)
        gtk.accel_map_add_entry("<hamster-time-tracker>/edit/prefs", gtk.keysyms.p, gtk.gdk.CONTROL_MASK)
        gtk.accel_map_add_entry("<hamster-time-tracker>/help/contents", gtk.keysyms.F1, 0)



        # create the status icon
        self.statusicon = ProjectHamsterStatusIcon(self)


        self.reposition_hamster_window()
        self.show_hamster_window()
        self.show_in_tray()

    def create_hamster_window(self):
        if self.window is None:
            # load window of activity switcher and todays view
            self._gui = load_ui_file("today.ui")
            self.window = self._gui.get_object('hamster-window')
            self.window.connect("delete_event", self.on_delete_window)

            gtk.window_set_default_icon_name("hamster-time-tracker")

            self.new_name = widgets.ActivityEntry()
            self.new_name.connect("value-entered", self.on_switch_activity_clicked)
            widgets.add_hint(self.new_name, _("Activity"))
            self.get_widget("new_name_box").add(self.new_name)
            self.new_name.connect("changed", self.on_activity_text_changed)

            self.new_tags = widgets.TagsEntry()
            self.new_tags.connect("tags_selected", self.on_switch_activity_clicked)
            widgets.add_hint(self.new_tags, _("Tags"))
            self.get_widget("new_tags_box").add(self.new_tags)

            self.tag_box = widgets.TagBox(interactive = False)
            self.get_widget("tag_box").add(self.tag_box)

            self.treeview = widgets.FactTree()
            self.treeview.connect("key-press-event", self.on_todays_keys)
            self.treeview.connect("edit-clicked", self._open_edit_activity)
            self.treeview.connect("row-activated", self.on_today_row_activated)

            self.get_widget("today_box").add(self.treeview)

            # connect the accelerators
            self.accel_group = self.get_widget("accelgroup")
            self.window.add_accel_group(self.accel_group)

            self._gui.connect_signals(self)
            
            # Signal for Redmine issue combo
            self.get_widget("issue_combo").connect("changed", self.on_redmine_issue_combo_change)
            
            # Signal for Redmine arbitrary issue id entry
            self.get_widget("arbitrary_issue_id_entry").connect("changed", self.on_redmine_arbitrary_issue_id_entry_change)
            
            # Redmine combos additional setup
            cell = gtk.CellRendererText()
            self.get_widget("issue_combo").pack_start(cell, True)
            self.get_widget("issue_combo").add_attribute(cell, 'text',0)
            cell = gtk.CellRendererText()
            self.get_widget("time_activity_combo").pack_start(cell, True)
            self.get_widget("time_activity_combo").add_attribute(cell, 'text',0)

    def reposition_hamster_window(self):
        if not self.window:
            self.create_hamster_window()

        if conf.get("standalone_window_maximized"):
            self.window.maximize()
        else:
            window_box = conf.get("standalone_window_box")
            if window_box:
                x,y,w,h = (int(i) for i in window_box)
                self.window.move(x, y)
                self.window.move(x, y)
                self.window.resize(w, h)
            else:
                self.window.set_position(gtk.WIN_POS_CENTER)

    def toggle_hamster_window(self):
        if not self.window:
            self.show_hamster_window()
        else:
            self.close_window()

    def show_hamster_window(self):
        if not self.window:
            self.create_hamster_window()
            self.reposition_hamster_window()

        self.window.show_all()
        self.refresh_hamster()


    def init_workspace_tracking(self):
        if not wnck: # can't track if we don't have the trackable
            return

        self.screen = wnck.screen_get_default()
        self.screen.workspace_handler = self.screen.connect("active-workspace-changed", self.on_workspace_changed)
        self.workspace_activities = {}

    """UI functions"""
    def refresh_hamster(self):
        """refresh hamster every x secs - load today, check last activity etc."""
        try:
            if self.window:
                self.load_day()
        except Exception, e:
            logging.error("Error while refreshing: %s" % e)
        finally:  # we want to go on no matter what, so in case of any error we find out about it sooner
            return True


    def load_day(self):
        """sets up today's tree and fills it with records
           returns information about last activity"""
        facts = self.todays_facts = runtime.storage.get_todays_facts()

        self.treeview.detach_model()

        if facts and facts[-1].end_time == None:
            self.last_activity = facts[-1]
        else:
            self.last_activity = None

        by_category = {}
        for fact in facts:
            duration = 24 * 60 * fact.delta.days + fact.delta.seconds // 60
            by_category[fact.category] = \
                          by_category.setdefault(fact.category, 0) + duration
            self.treeview.add_fact(fact)

        self.treeview.attach_model()

        if not facts:
            self._gui.get_object("today_box").hide()
            self._gui.get_object("fact_totals").set_text(_("No records today"))
        else:
            self._gui.get_object("today_box").show()
            total_strings = []
            for category in by_category:
                # listing of today's categories and time spent in them
                duration = locale.format("%.1f", (by_category[category] / 60.0))
                total_strings.append(_("%(category)s: %(duration)s") % \
                        ({'category': category,
                          #duration in main drop-down per category in hours
                          'duration': _("%sh") % duration
                          }))

            total_string = ", ".join(total_strings)
            self._gui.get_object("fact_totals").set_text(total_string)
        
        # Before setting last activity make sure that Redmine stuff is visible only if the integration is enabled (i. e. hide the widgets now and leave the rest to the code in set_last_activity())
        self.get_widget("redmine_frame").hide()
        

        self.set_last_activity()


    def set_last_activity(self):
        activity = self.last_activity
        #sets all the labels and everything as necessary
        self.get_widget("stop_tracking").set_sensitive(activity != None)
        arbitrary_issue_id = self.get_widget("arbitrary_issue_id_entry").get_text()
        active_activity = self.get_widget("time_activity_combo").get_active()


        if activity:
            self.get_widget("switch_activity").show()
            self.get_widget("start_tracking").hide()
            
            # If the Redmine integration is enabled, show the Redmine frame and set insensitivity of combos
            if conf.get("redmine_integration_enabled"):
              self.get_widget("redmine_frame").show()
              self.get_widget("issue_combo").set_sensitive(False)
              self.get_widget("time_activity_combo").set_sensitive(False)
              self.get_widget("arbitrary_issue_id_entry").set_sensitive(False)
              if arbitrary_issue_id != None:
                self.get_widget("arbitrary_issue_id_entry").set_text(arbitrary_issue_id)
                self.get_widget("time_activity_combo").set_active(active_activity)

            delta = dt.datetime.now() - activity.start_time
            duration = delta.seconds //  60

            if activity.category != _("Unsorted"):
                if isinstance(activity, RedmineFact):
                    self.get_widget("last_activity_name").set_text("%s %s - %s" %(activity.activity, activity.redmine_tag(), activity.category))
                else:
                    self.get_widget("last_activity_name").set_text("%s - %s" %(activity.activity, activity.category))
            else:
                if isinstance(activity, RedmineFact):
                    self.get_widget("last_activity_name").set_text("%s %s"%(activity.activity, activity.redmine_tag()))
                else:
                    self.get_widget("last_activity_name").set_text(activity.activity)

            self.get_widget("last_activity_duration").set_text(stuff.format_duration(duration) or _("Just started"))
            self.get_widget("last_activity_description").set_text(activity.description or "")
            self.get_widget("activity_info_box").show()

            self.tag_box.draw(activity.tags)
        else:
            self.get_widget("switch_activity").hide()
            self.get_widget("start_tracking").show()

            self.get_widget("last_activity_name").set_text(_("No activity"))

            self.get_widget("activity_info_box").hide()

            self.tag_box.draw([])
            
            # If the Redmine integration is enabled, show the Redmine frame and set up the combos (if there is no selection), making sure they are sensitive
            if conf.get("redmine_integration_enabled"):
              self.get_widget("redmine_frame").show()
              self.get_widget("issue_combo").set_sensitive(True)
              self.get_widget("time_activity_combo").set_sensitive(True)
              if self.get_widget("issue_combo").get_active() == -1 or self.get_widget("issue_combo").get_active() == 0:
                self.fill_issues_combo()
                self.get_widget("arbitrary_issue_id_entry").set_sensitive(True)
              if self.get_widget("time_activity_combo").get_active() == -1 or self.get_widget("time_activity_combo").get_active() == 0:
                self.fill_time_activities_combo()
              if arbitrary_issue_id != None:
                self.get_widget("arbitrary_issue_id_entry").set_text(arbitrary_issue_id)
                self.get_widget("time_activity_combo").set_active(active_activity)

    def delete_selected(self):
        fact = self.treeview.get_selected_fact()
        runtime.storage.remove_fact(fact.id)


    """events"""
    def on_todays_keys(self, tree, event):
        if (event.keyval == gtk.keysyms.Delete):
            self.delete_selected()
            return True

        return False

    def _open_edit_activity(self, row, fact):
        """opens activity editor for selected row"""
        dialogs.edit.show(self.window, fact_id = fact.id)

    def on_today_row_activated(self, tree, path, column):
        fact = tree.get_selected_fact()
        fact = Fact(fact.activity,
                          category = fact.category,
                          description = fact.description,
                          tags = ", ".join(fact.tags))
        if fact.activity:
            runtime.storage.add_fact(fact)

    def on_add_activity_clicked(self, button):
        dialogs.edit.show(self.window)

    def on_show_overview_clicked(self, button):
        dialogs.overview.show(self.window)


    """button events"""
    def on_menu_add_earlier_activate(self, menu):
        dialogs.edit.show(self.window)
    def on_menu_overview_activate(self, menu_item):
        dialogs.overview.show(self.window)
    def on_menu_about_activate(self, component):
        dialogs.about.show(self.window)
    def on_menu_statistics_activate(self, component):
        dialogs.stats.show(self.window)
    def on_menu_preferences_activate(self, menu_item):
        dialogs.prefs.show(self.window)
    def on_menu_help_contents_activate(self, *args):
        gtk.show_uri(gtk.gdk.Screen(), "ghelp:hamster-time-tracker", 0L)
        trophies.unlock("basic_instructions")


    """signals"""
    def after_activity_update(self, widget):
        self.new_name.refresh_activities()
        self.load_day()

    def after_fact_update(self, event):
        self.load_day()

    def on_workspace_changed(self, screen, previous_workspace):
        if not previous_workspace:
            # wnck has a slight hiccup on init and after that calls
            # workspace changed event with blank previous state that should be
            # ignored
            return

        if not self.workspace_tracking:
            return # default to not doing anything

        current_workspace = screen.get_active_workspace()

        # rely on workspace numbers as names change
        prev = previous_workspace.get_number()
        new = current_workspace.get_number()

        # on switch, update our mapping between spaces and activities
        self.workspace_activities[prev] = self.last_activity


        activity = None
        if "name" in self.workspace_tracking:
            # first try to look up activity by desktop name
            mapping = conf.get("workspace_mapping")

            fact = None
            if new < len(mapping):
                fact = Fact(mapping[new])

                if fact.activity:
                    category_id = None
                    if fact.category:
                        category_id = runtime.storage.get_category_id(fact.category)

                    activity = runtime.storage.get_activity_by_name(fact.activity,
                                                                    category_id,
                                                                    resurrect = False)
                    if activity:
                        # we need dict below
                        activity = dict(name = activity.name,
                                        category = activity.category,
                                        description = fact.description,
                                        tags = fact.tags)


        if not activity and "memory" in self.workspace_tracking:
            # now see if maybe we have any memory of the new workspace
            # (as in - user was here and tracking Y)
            # if the new workspace is in our dict, switch to the specified activity
            if new in self.workspace_activities and self.workspace_activities[new]:
                activity = self.workspace_activities[new]

        if not activity:
            return

        # check if maybe there is no need to switch, as field match:
        if self.last_activity and \
           self.last_activity.name.lower() == activity.name.lower() and \
           (self.last_activity.category or "").lower() == (activity.category or "").lower() and \
           ", ".join(self.last_activity.tags).lower() == ", ".join(activity.tags).lower():
            return

        # ok, switch
        fact = Fact(activity.name,
                          tags = ", ".join(activity.tags),
                          category = activity.category,
                          description = activity.description);
        runtime.storage.add_fact(fact)


    def on_toggle_called(self, client):
        self.window.present()

    def on_conf_changed(self, event, key, value):
        if key == "day_start_minutes":
            self.load_day()

        elif key == "workspace_tracking":
            self.workspace_tracking = value
            if self.workspace_tracking and not self.screen:
                self.init_workspace_tracking()
            elif not self.workspace_tracking:
                if self.screen:
                    self.screen.disconnect(self.screen.workspace_handler)
                    self.screen = None

    def on_activity_text_changed(self, widget):
        self.get_widget("switch_activity").set_sensitive(widget.get_text() != "")

    def on_switch_activity_clicked(self, widget):
        activity, temporary = self.new_name.get_value()
        
        # Redmine integration - if activity is connected with Redmine, it must use new data structures to save additional data
        fact = None
        if conf.get("redmine_integration_enabled"):
            redmine_issue_subject = self.get_widget("issue_combo").get_active_text()
            if redmine_issue_subject == None or redmine_issue_subject == "None":
              arbitrary_issue_id = self.get_widget("arbitrary_issue_id_entry").get_text()
              if arbitrary_issue_id == "" or arbitrary_issue_id == None:
                fact = Fact(activity, tags = self.new_tags.get_text().decode("utf8", "replace"))
              else:
                redcon = redmine.RedmineConnector(conf.get("redmine_url"), conf.get("redmine_api_key"))
                try:
                  redcon.get_arbitrary_issue_data(arbitrary_issue_id)
                  arbitrary_issue_id = int(arbitrary_issue_id)
                  redmine_time_activity_name = self.get_widget("time_activity_combo").get_active_text()
                  if redmine_time_activity_name == None:
                    dialog = gtk.Dialog("Failed to start tracking", self.window, gtk.DIALOG_MODAL, (gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
                    label = gtk.Label("Redmine activity cannot be empty!")
                    dialog.vbox.pack_start(label)
                    label.show()
                    dialog.run()
                    dialog.destroy()
                    return
                  redmine_activity_id = redcon.get_redmine_activity_id(redmine_time_activity_name)
                  fact = RedmineFact(activity, arbitrary_issue_id, redmine_activity_id, tags = self.new_tags.get_text().decode("utf8", "replace"))
                except redmine.RedmineConnectionException:
                  dialog = gtk.Dialog("Failed to start tracking", self.window, gtk.DIALOG_MODAL, (gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
                  label = gtk.Label("Invalid arbitrary issue number!")
                  dialog.vbox.pack_start(label)
                  label.show()
                  dialog.run()
                  dialog.destroy()
                  return
            else:
                redmine_time_activity_name = self.get_widget("time_activity_combo").get_active_text()
                if redmine_time_activity_name == None:
                    dialog = gtk.Dialog("Failed to start tracking", self.window, gtk.DIALOG_MODAL, (gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
                    label = gtk.Label("Redmine activity cannot be empty!")
                    dialog.vbox.pack_start(label)
                    label.show()
                    dialog.run()
                    dialog.destroy()
                    return
                redcon = redmine.RedmineConnector(conf.get("redmine_url"), conf.get("redmine_api_key"))
                redmine_issue_id = redcon.get_redmine_issue_id(redmine_issue_subject)
                redmine_activity_id = redcon.get_redmine_activity_id(redmine_time_activity_name)
                fact = RedmineFact(activity, redmine_issue_id, redmine_activity_id, tags = self.new_tags.get_text().decode("utf8", "replace"))
        else:
            fact = Fact(activity, tags = self.new_tags.get_text().decode("utf8", "replace"))
            
        if not fact.activity:
            return

        runtime.storage.add_fact(fact, temporary)
        self.new_name.set_text("")
        self.new_tags.set_text("")

    def on_stop_tracking_clicked(self, widget):
        facts = runtime.storage.get_todays_facts()
        fact = facts[-1]
        runtime.storage.stop_tracking()
        self.last_activity = None
        if fact != None and conf.get("redmine_integration_enabled") and (fact.delta.days * 24 + fact.delta.seconds / 3600) >= 0.016 and not fact.redmine_issue_id == -1:
            redmine_url = conf.get("redmine_url")
            redmine_api_key = conf.get("redmine_api_key")
            redcon = redmine.RedmineConnector(redmine_url, redmine_api_key)
            redcon.add_time_entry(fact.redmine_issue_id, round((fact.delta.days * 24 + fact.delta.seconds / 3600), 2), fact.redmine_time_activity_id, fact.activity)
        self.fill_issues_combo()
        self.fill_time_activities_combo()

    def on_window_configure_event(self, window, event):
        self.treeview.fix_row_heights()

    def show(self):
        self.window.show_all()
        self.window.present()

    def get_widget(self, name):
        return self._gui.get_object(name)

    def on_more_info_button_clicked(self, *args):
        gtk.show_uri(gtk.gdk.Screen(), "ghelp:hamster-time-tracker#input", 0L)
        return False

    def save_window_position(self):
        # properly saving window state and position
        maximized = self.window.get_window().get_state() & gtk.gdk.WINDOW_STATE_MAXIMIZED
        conf.set("standalone_window_maximized", maximized)

        # make sure to remember dimensions only when in normal state
        if maximized == False and not self.window.get_window().get_state() & gtk.gdk.WINDOW_STATE_ICONIFIED:
            x, y = self.window.get_position()
            w, h = self.window.get_size()
            conf.set("standalone_window_box", [x, y, w, h])

    def quit_app(self, *args):
        self.save_window_position()

        # quit the application
        gtk.main_quit()

    def close_window(self, *args):
        self.save_window_position()
        self.window.destroy()
        self.window = None

    def on_delete_window(self, event, data):
        self.save_window_position()
        self.window.destroy()
        self.window = None

    def show_in_tray(self):
        # show the status tray icon
        activity = self.get_widget("last_activity_name").get_text()
        self.statusicon.set_tooltip(activity)
        self.statusicon.set_visible(True)
        
    # Redmine functions
    def fill_issues_combo(self):
      combomodel = self.get_widget("issue_combo").get_model()
      if combomodel == None:
        combomodel = gtk.ListStore(gobject.TYPE_STRING)
      combomodel.clear()
      self.get_widget("issue_combo").set_model(None) # Optimizes operations
      if conf.get("redmine_integration_enabled"):
        redmine_url = conf.get("redmine_url")
        redmine_api_key = conf.get("redmine_api_key")
        redcon = redmine.RedmineConnector(redmine_url, redmine_api_key)
        issues = redcon.get_issues()
        combomodel.append(["None"])
        for issue in issues['issues']:
          combomodel.append([issue["subject"]])
      else:
        combomodel = None
      self.get_widget("issue_combo").set_model(combomodel)
      self.get_widget("issue_combo").set_active(0)
            
    def fill_time_activities_combo(self):
      combomodel = self.get_widget("time_activity_combo").get_model()
      if combomodel == None:
        combomodel = gtk.ListStore(gobject.TYPE_STRING)
      combomodel.clear()
      self.get_widget("time_activity_combo").set_model(None) # Optimizes operations
      if conf.get("redmine_integration_enabled"):
        redmine_url = conf.get("redmine_url")
        redmine_api_key = conf.get("redmine_api_key")
        redcon = redmine.RedmineConnector(redmine_url, redmine_api_key)
        activities = redcon.get_activities()
        for activity in activities['time_entry_activities']:
          combomodel.append([activity["name"]])
      else:
        combomodel = None
      self.get_widget("time_activity_combo").set_model(combomodel)
        
    # Redmine callbacks
    def on_redmine_issue_combo_change(self, combobox):
      redmine_url = conf.get("redmine_url")
      redmine_api_key = conf.get("redmine_api_key")
      redcon = redmine.RedmineConnector(redmine_url, redmine_api_key)
      if combobox.get_active() == 0:
        self.get_widget("time_activity_combo").set_sensitive(False)
        self.get_widget("time_activity_combo").set_active(-1)
        self.get_widget("arbitrary_issue_id_entry").set_sensitive(True)
        self.get_widget("arbitrary_issue_id_entry").set_text("")
      else:
        self.get_widget("time_activity_combo").set_sensitive(True)
        self.get_widget("arbitrary_issue_id_entry").set_sensitive(False)
        
    def on_redmine_arbitrary_issue_id_entry_change(self, entry):
      if entry.get_text() == "" or entry.get_text() == None:
        self.get_widget("time_activity_combo").set_sensitive(False)
        self.get_widget("time_activity_combo").set_active(-1)
        self.get_widget("issue_combo").set_sensitive(True)
      else:
        self.get_widget("time_activity_combo").set_sensitive(True)
        self.get_widget("issue_combo").set_sensitive(False)
        self.get_widget("issue_combo").set_active(0)
