import subprocess
import time
import os

from i18n import _
from gi.repository import Gtk as gtk
from gi.repository import GObject as gobject

def run_howdy(cmd_list):
	"""Run howdy command with pkexec if not root"""
	cmd = cmd_list if isinstance(cmd_list, list) else cmd_list.split()
	
	if os.geteuid() != 0:
		if cmd[0] != "pkexec":
			cmd = ["pkexec"] + cmd
			
	return subprocess.getstatusoutput(" ".join(cmd))


def on_user_change(self, select):
	self.active_user = select.get_active_text()
	self.load_model_list()


def on_user_add(self, button):
	# Open question dialog
	dialog = gtk.MessageDialog(parent=self, flags=gtk.DialogFlags.MODAL, type=gtk.MessageType.QUESTION, buttons=gtk.ButtonsType.OK_CANCEL)
	dialog.set_title(_("Confirm User Creation"))
	dialog.props.text = _("Please enter the username of the user you want to add to Howdy")

	# Create the input field
	entry = gtk.Entry()

	# Add a label to ask for a model name
	hbox = gtk.HBox()
	hbox.pack_start(gtk.Label(_("Username:")), False, 5, 5)
	hbox.pack_end(entry, True, True, 5)

	# Add the box and show the dialog
	dialog.vbox.pack_end(hbox, True, True, 0)
	dialog.show_all()

	# Show dialog
	response = dialog.run()

	entered_user = entry.get_text()
	dialog.destroy()

	if response == gtk.ResponseType.OK:
		self.userlist.append_text(entered_user)
		self.userlist.set_active(self.userlist.items)
		self.userlist.items += 1

		self.active_user = entered_user
		self.load_model_list()


def on_model_add(self, button):
	if self.userlist.items == 0:
		return
	# Open question dialog
	dialog = gtk.MessageDialog(parent=self, flags=gtk.DialogFlags.MODAL, type=gtk.MessageType.QUESTION, buttons=gtk.ButtonsType.OK_CANCEL)
	dialog.set_title(_("Confirm Model Creation"))
	dialog.props.text = _("Please enter a name for the new model, 24 characters max")

	# Create the input field
	entry = gtk.Entry()

	# Add a label to ask for a model name
	hbox = gtk.HBox()
	hbox.pack_start(gtk.Label(_("Model name:")), False, 5, 5)
	hbox.pack_end(entry, True, True, 5)

	# Add the box and show the dialog
	dialog.vbox.pack_end(hbox, True, True, 0)
	dialog.show_all()

	# Show dialog
	response = dialog.run()

	entered_name = entry.get_text()
	dialog.destroy()

	if response == gtk.ResponseType.OK:
		dialog = gtk.MessageDialog(parent=self, flags=gtk.DialogFlags.MODAL, buttons=gtk.ButtonsType.NONE)
		dialog.set_title(_("Creating Model"))
		dialog.props.text = _("Please look directly into the camera")
		dialog.show_all()

		# Wait a bit to allow the user to read the dialog
		def delayed_add():
			execute_add(self, dialog, entered_name)
			return False  # Important: return False to prevent repeat
		
		gobject.timeout_add(600, delayed_add)


def execute_add(box, dialog, entered_name):
	print(f"DEBUG: Adding model '{entered_name}' for user '{box.active_user}'")
	
	status, output = run_howdy(["howdy", "-U", box.active_user, "-y", "add", entered_name])
	
	print(f"DEBUG: Add command status={status}, output={repr(output)}")
	
	dialog.destroy()

	if status != 0:
		error_dialog = gtk.MessageDialog(parent=box, flags=gtk.DialogFlags.MODAL, type=gtk.MessageType.ERROR, buttons=gtk.ButtonsType.CLOSE)
		error_dialog.set_title(_("Howdy Error"))
		error_dialog.props.text = _("Error while adding model, error code {}: \n\n").format(str(status))
		error_dialog.format_secondary_text(output)
		error_dialog.run()
		error_dialog.destroy()
	else:
		print(f"DEBUG: Model added successfully")

	box.load_model_list()

def on_model_delete(self, button):
	selection = self.treeview.get_selection()
	(listmodel, rowlist) = selection.get_selected_rows()

	if len(rowlist) == 1:
		id = listmodel.get_value(listmodel.get_iter(rowlist[0]), 0)
		name = listmodel.get_value(listmodel.get_iter(rowlist[0]), 2)

		dialog = gtk.MessageDialog(parent=self, flags=gtk.DialogFlags.MODAL, buttons=gtk.ButtonsType.OK_CANCEL)
		dialog.set_title(_("Confirm Model Deletion"))
		dialog.props.text = _("Are you sure you want to delete model {id} ({name})?").format(id=id, name=name)
		response = dialog.run()
		dialog.destroy()

		if response == gtk.ResponseType.OK:
			status, output = run_howdy(["howdy", "remove", id, "-y", "-U", self.active_user])

			if status != 0:
				dialog = gtk.MessageDialog(parent=self, flags=gtk.DialogFlags.MODAL, type=gtk.MessageType.ERROR, buttons=gtk.ButtonsType.CLOSE)
				dialog.set_title(_("Howdy Error"))
				dialog.props.text = _("Error while deleting model, error code {}: \n\n").format(status)
				dialog.format_secondary_text(output)
				dialog.run()
				dialog.destroy()

			self.load_model_list()

def on_models_clear(self, button):
	"""Clear all models for the active user"""
	if not self.active_user:
		return

	dialog = gtk.MessageDialog(parent=self, flags=gtk.DialogFlags.MODAL, buttons=gtk.ButtonsType.OK_CANCEL)
	dialog.set_title(_("Confirm Clear All"))
	dialog.props.text = _("Are you sure you want to delete ALL models for {}?").format(self.active_user)
	response = dialog.run()
	dialog.destroy()

	if response == gtk.ResponseType.OK:
		status, output = run_howdy(["howdy", "clear", "-y", "-U", self.active_user])

		if status != 0:
			dialog = gtk.MessageDialog(parent=self, flags=gtk.DialogFlags.MODAL, type=gtk.MessageType.ERROR, buttons=gtk.ButtonsType.CLOSE)
			dialog.set_title(_("Howdy Error"))
			dialog.props.text = _("Error while clearing models, error code {}: \n\n").format(status)
			dialog.format_secondary_text(output)
			dialog.run()
			dialog.destroy()

		self.load_model_list()

def on_snapshot(self, button):
	"""Take a snapshot"""
	dialog = gtk.MessageDialog(parent=self, flags=gtk.DialogFlags.MODAL, buttons=gtk.ButtonsType.NONE)
	dialog.set_title(_("Taking Snapshot"))
	dialog.props.text = _("Please look directly into the camera")
	dialog.show_all()

	# Wait a bit
	def delayed_snapshot():
		execute_snapshot(self, dialog)
		return False  # Important: return False to prevent repeat
	
	gobject.timeout_add(600, delayed_snapshot)

def execute_snapshot(box, dialog):
	status, output = run_howdy(["howdy", "snapshot"])
	
	dialog.destroy()
	
	if status != 0:
		error_dialog = gtk.MessageDialog(parent=box, flags=gtk.DialogFlags.MODAL, type=gtk.MessageType.ERROR, buttons=gtk.ButtonsType.CLOSE)
		error_dialog.set_title(_("Snapshot Error"))
		error_dialog.props.text = _("Error while taking snapshot, error code {}: \n\n").format(str(status))
		error_dialog.format_secondary_text(output)
		error_dialog.run()
		error_dialog.destroy()
	else:
		# Parse output for filename
		lines = output.splitlines()
		filename = lines[-1] if lines else _("Unknown file")
		
		success_dialog = gtk.MessageDialog(parent=box, flags=gtk.DialogFlags.MODAL, type=gtk.MessageType.INFO, buttons=gtk.ButtonsType.OK)
		success_dialog.set_title(_("Snapshot Saved"))
		success_dialog.props.text = _("Snapshot saved to:\n{}").format(filename)
		success_dialog.run()
		success_dialog.destroy()
