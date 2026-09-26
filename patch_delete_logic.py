# CatLogs
# A local system logging and diagnostic tool.
# Copyright (C) 2026 Wassim Bolles
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import re

with open("catlogs/gui.py", "r") as f:
    content = f.read()

# Fix _delete_selected_log
old_delete = """        if confirm:
            log_deletion("Command Delete", f"Deleted command: {cmd}", True)
            self.tree.delete(item_id)
            # Find in self.all_logs and remove
            for log in getattr(self, 'all_logs', []):
                if hasattr(log, 'command') and log.command == cmd:
                    self.all_logs.remove(log)
                    break
            self._apply_filters()"""

new_delete = """        if confirm:
            log_deletion("Command Delete", f"Deleted command: {cmd}", True)
            from .deleted_logs import add_deleted_log
            add_deleted_log(cmd)
            self.tree.delete(item_id)
            
            # Find in self.all_entries and remove
            for i in range(len(self.all_entries) - 1, -1, -1):
                if hasattr(self.all_entries[i], 'command') and self.all_entries[i].command == cmd:
                    del self.all_entries[i]
                    
            self._apply_filters()"""

content = content.replace(old_delete, new_delete)

# Fix _on_collection_done
old_collection = """    def _on_collection_done(self, entries: List[CommandEntry]):
        self.all_entries = entries"""

new_collection = """    def _on_collection_done(self, entries: List[CommandEntry]):
        from .deleted_logs import load_deleted_logs
        deleted = set(load_deleted_logs())
        self.all_entries = [e for e in entries if getattr(e, 'command', '') not in deleted]"""

content = content.replace(old_collection, new_collection)

with open("catlogs/gui.py", "w") as f:
    f.write(content)
