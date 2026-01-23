# Opens and controls main ui window
import gi
import signal
import sys
import os
import subprocess

from i18n import _
import paths_factory
import tray

# Make sure we have the libs we need
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

# Import them
from gi.repository import Gtk as gtk


class MainWindow(gtk.Window):
	def __init__(self):
		"""Initialize the sticky window"""
		# Make the class a GTK window
		gtk.Window.__init__(self)

		self.builder = gtk.Builder()
		self.builder.add_from_file(paths_factory.main_window_wireframe_path())
		self.builder.connect_signals(self)

		self.window = self.builder.get_object("mainwindow")
		self.userlist = self.builder.get_object("userlist")
		self.modellistbox = self.builder.get_object("modellistbox")
		self.opencvimage = self.builder.get_object("opencvimage")

		self.window.connect("destroy", self.exit)
		self.window.connect("delete_event", self.hide_to_tray)

		# Init tray icon
		self.tray = tray.TrayIcon(self)

		# Init capture for video tab
		self.capture = None

		# Create a treeview that will list the model data
		self.treeview = gtk.TreeView()
		self.treeview.set_vexpand(True)

		# Set the columns
		for i, column in enumerate([_("ID"), _("Created"), _("Label")]):
			col = gtk.TreeViewColumn(column, gtk.CellRendererText(), text=i)
			self.treeview.append_column(col)

		# Add the treeview
		self.modellistbox.add(self.treeview)

		filelist = os.listdir(paths_factory.user_models_dir_path())
		self.active_user = ""

		self.userlist.items = 0

		for file in filelist:
			self.userlist.append_text(file[:-4])
			self.userlist.items += 1

			if not self.active_user:
				self.active_user = file[:-4]

		self.userlist.set_active(0)
		
		# Explicitly load models if we have an active user (since set_active(0) doesn't always trigger changed signal)
		if self.active_user:
			self.load_model_list()

		if "--minimized" not in sys.argv:
			self.window.show_all()

		# Start GTK main loop
		gtk.main()

	def hide_to_tray(self, widget, event):
		"""Hide the window to tray instead of closing"""
		self.window.hide()
		return True

	def show_from_tray(self):
		"""Show the window from tray"""
		self.window.show_all()
		self.window.present()

	def load_model_list(self):
		"""(Re)load the model list"""
		import json
		import time
		import paths_factory

		# Get username and default to none if there are no models at all yet
		user = 'none'
		if self.active_user: user = self.active_user

		# Create a datamodel
		self.listmodel = gtk.ListStore(str, str, str)

		# Try to read models file directly (no need for sudo)
		try:
			models_file = paths_factory.user_model_path(user)
			print(f"DEBUG: Reading models from: {models_file}")
			
			with open(models_file, 'r') as f:
				encodings = json.load(f)
			
			print(f"DEBUG: Loaded {len(encodings)} models")
			
			# Add each model to the list
			for enc in encodings:
				model_id = str(enc["id"])
				# Format time as ISO in local timezone
				model_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(enc["time"]))
				model_label = enc["label"]
				
				print(f"DEBUG: Adding model: {model_id}, {model_time}, {model_label}")
				self.listmodel.append([model_id, model_time, model_label])
		
		except FileNotFoundError:
			print(f"DEBUG: No models file found for user {user}")
		except PermissionError as e:
			print(f"DEBUG: Permission error reading models: {e}")
		except Exception as e:
			print(f"DEBUG: Error loading models: {e}")
			import traceback
			traceback.print_exc()

		self.treeview.set_model(self.listmodel)
		print(f"DEBUG: Model set, total rows: {len(self.listmodel)}")

	def on_about_link(self, label, uri):
		"""Open links on about page"""
		# If running as root (via sudo), try to downgrade to user
		if os.geteuid() == 0:
			try:
				user = os.getlogin()
			except Exception:
				user = os.environ.get("SUDO_USER")
			
			if user:
				subprocess.getstatusoutput(["sudo -u " + user + " timeout 10 xdg-open " + uri])
				return True
				
		# Running as user
		subprocess.getstatusoutput(["timeout 10 xdg-open " + uri])
		return True

	def exit(self, widget=None, context=None):
		"""Cleanly exit"""
		if self.capture is not None:
			self.capture.release()

		gtk.main_quit()
		sys.exit(0)


# Make sure we quit on a SIGINT
signal.signal(signal.SIGINT, signal.SIG_DFL)

# Make sure we run as sudo
# Removed root check to allow tray icon to work as user
# Commands requiring root will use pkexec

# If no models have been created yet or when it is forced, start the onboarding
if "--force-onboarding" in sys.argv or not os.path.exists(paths_factory.user_models_dir_path()):
	import onboarding
	onboarding.OnboardingWindow()

	sys.exit(0)

# Class is split so it isn't too long, import split functions
import tab_models
MainWindow.on_user_add = tab_models.on_user_add
MainWindow.on_user_change = tab_models.on_user_change
MainWindow.on_model_add = tab_models.on_model_add
MainWindow.on_model_delete = tab_models.on_model_delete
MainWindow.on_models_clear = tab_models.on_models_clear
MainWindow.on_snapshot = tab_models.on_snapshot

import tab_video
MainWindow.capture_frame = tab_video.capture_frame

import tab_config
MainWindow.on_config_save = tab_config.on_config_save
MainWindow.on_config_open_editor = tab_config.on_config_open_editor

# Lazy import of tab_test to avoid loading opencv at startup
# It will be loaded only when Test tab is accessed
_tab_test_module = None

def _get_tab_test():
	"""Lazy load tab_test module"""
	global _tab_test_module
	if _tab_test_module is None:
		try:
			print("DEBUG: Attempting to load tab_test module...")
			import tab_test
			_tab_test_module = tab_test
			print("DEBUG: tab_test loaded successfully")
		except ImportError as e:
			print(f"ERROR: tab_test not available: {e}")
			import traceback
			traceback.print_exc()
			_tab_test_module = False
		except Exception as e:
			print(f"ERROR: Unexpected error loading tab_test: {e}")
			import traceback
			traceback.print_exc()
			_tab_test_module = False
	return _tab_test_module if _tab_test_module else None

def toggle_test_wrapper(self, button):
	"""Wrapper for toggle_test with lazy loading"""
	print(f"DEBUG: toggle_test_wrapper called, button={button.get_label()}")
	tab_test = _get_tab_test()
	if tab_test:
		print("DEBUG: Calling tab_test.toggle_test")
		tab_test.toggle_test(self, button)
	else:
		print("ERROR: Test tab not available (missing opencv/numpy/dlib)")
		# Show error dialog to user
		import gi
		gi.require_version('Gtk', '3.0')
		from gi.repository import Gtk
		dialog = Gtk.MessageDialog(
			parent=self.window,
			flags=Gtk.DialogFlags.MODAL,
			type=Gtk.MessageType.ERROR,
			buttons=Gtk.ButtonsType.OK
		)
		dialog.set_title("Test Tab Unavailable")
		dialog.props.text = "Test tab requires additional dependencies:\npython-opencv, python-numpy, and dlib"
		dialog.run()
		dialog.destroy()

def toggle_slow_mode_wrapper(self, button):
	"""Wrapper for toggle_slow_mode with lazy loading"""
	tab_test = _get_tab_test()
	if tab_test:
		tab_test.toggle_slow_mode(self, button)

MainWindow.toggle_test = toggle_test_wrapper
MainWindow.toggle_slow_mode = toggle_slow_mode_wrapper

def on_page_switch(self, notebook, page, page_num):
	# Video Tab logic
	tab_video.on_page_switch(self, notebook, page, page_num)
	
	# Config Tab
	if page_num == 2:
		tab_config.on_config_switch(self)
		
	# Test Tab
	if page_num == 3:
		tab_test = _get_tab_test()
		if tab_test:
			tab_test.init_test_tab(self)
		else:
			# Show error message in UI if opencv is not available
			print("Test tab not available. Please install: pip3 install numpy opencv-python")
	else:
		if hasattr(self, 'test_running') and self.test_running:
			tab_test = _get_tab_test()
			if tab_test:
				tab_test.stop_test(self)
				self.builder.get_object("testtoggle").set_label(_("Start Test"))

MainWindow.on_page_switch = on_page_switch

# Open the GTK window
window = MainWindow()
