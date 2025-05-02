import tkinter as tk
from tkinter import scrolledtext, messagebox, font as tkFont
import requests
import time
import json
import datetime
import threading # To run blocking tasks without freezing the GUI
import queue      # To communicate between threads
import os         # <-- Added for file path operations

# --- Config Filename ---
CONFIG_FILENAME = "myconfig.json" # <-- Added constant

PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"

# --- Time Window Defaults (can be adjusted here) ---
MORNING_START_HOUR = 8
MORNING_END_HOUR = 12
AFTERNOON_START_HOUR = 16
AFTERNOON_END_HOUR = 19
CHECK_INTERVAL_SECONDS = 15 # How often to check status
RUN_DURATION_MINUTES = 30   # How long to run after starting

# --- API URLs ---
STATION_INFO_URL = "https://gbfs.bluebikes.com/gbfs/en/station_information.json"
STATION_STATUS_URL = "https://gbfs.bluebikes.com/gbfs/en/station_status.json"

# --- GUI Application Class ---
class BluebikesTrackerApp:
    def __init__(self, master):
        self.master = master
        master.title("Bluebikes E-Bike Tracker")
        master.geometry("750x700") # Adjust size as needed

        # --- State Variables ---
        self.tracking_active = False
        self.tracking_thread = None
        self.stop_event = threading.Event()
        self.result_queue = queue.Queue()
        self.station_names = None
        self.previous_ebike_status = {}
        self.current_station_ids_to_track = []
        self.pushover_token = ""
        self.pushover_user_key = ""
        self.start_time = None
        self.run_duration_seconds = RUN_DURATION_MINUTES * 60
        self.end_time = None
        self.tracking_mode = None
        self.timer_update_id = None

        # --- Font ---
        self.default_font = tkFont.nametofont("TkDefaultFont")
        self.default_font.configure(size=10)
        self.bold_font = tkFont.Font(family=self.default_font['family'], size=self.default_font['size'], weight='bold')

        # --- GUI Layout ---
        # PanedWindow for resizable sections
        self.paned_window = tk.PanedWindow(master, orient=tk.VERTICAL, sashrelief=tk.RAISED)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Top Frame: Configuration
        self.config_frame = tk.Frame(self.paned_window, bd=2, relief=tk.GROOVE)
        self.paned_window.add(self.config_frame, minsize=200)

        # Middle Frame: Controls and Status
        self.controls_frame = tk.Frame(self.paned_window, height=60)
        self.paned_window.add(self.controls_frame, stretch="never") # Don't stretch this frame vertically

        # Bottom Frame: Logs
        self.log_frame = tk.Frame(self.paned_window, bd=2, relief=tk.GROOVE)
        self.paned_window.add(self.log_frame, minsize=200)


        # --- Configuration Widgets ---
        config_inner_frame = tk.Frame(self.config_frame)
        config_inner_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Pushover Credentials
        pushover_frame = tk.LabelFrame(config_inner_frame, text="Pushover Credentials", padx=5, pady=5, font=self.bold_font)
        pushover_frame.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        pushover_frame.columnconfigure(1, weight=1)

        tk.Label(pushover_frame, text="API Token/Key:").grid(row=0, column=0, sticky="w", padx=2)
        self.pushover_token_entry = tk.Entry(pushover_frame, width=40)
        self.pushover_token_entry.grid(row=0, column=1, sticky="ew", padx=2)
        # Value will be set by load_configuration

        tk.Label(pushover_frame, text="User Key:").grid(row=1, column=0, sticky="w", padx=2)
        self.pushover_user_key_entry = tk.Entry(pushover_frame, width=40)
        self.pushover_user_key_entry.grid(row=1, column=1, sticky="ew", padx=2)
        # Value will be set by load_configuration

        # Station IDs
        stations_frame = tk.Frame(config_inner_frame)
        stations_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        config_inner_frame.rowconfigure(1, weight=1)
        config_inner_frame.columnconfigure(0, weight=1)
        config_inner_frame.columnconfigure(1, weight=1)

        # Morning Stations
        morning_frame = tk.LabelFrame(stations_frame, text=f"Morning Stations ({MORNING_START_HOUR:02d}:00 - {MORNING_END_HOUR:02d}:00)", padx=5, pady=5, font=self.bold_font)
        morning_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        morning_frame.rowconfigure(0, weight=1)
        morning_frame.columnconfigure(0, weight=1)
        self.morning_stations_text = scrolledtext.ScrolledText(morning_frame, wrap=tk.WORD, height=8, width=40)
        self.morning_stations_text.grid(row=0, column=0, sticky="nsew")
        # Value will be set by load_configuration

        # Afternoon Stations
        afternoon_frame = tk.LabelFrame(stations_frame, text=f"Afternoon Stations ({AFTERNOON_START_HOUR:02d}:00 - {AFTERNOON_END_HOUR:02d}:00)", padx=5, pady=5, font=self.bold_font)
        afternoon_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        afternoon_frame.rowconfigure(0, weight=1)
        afternoon_frame.columnconfigure(0, weight=1)
        self.afternoon_stations_text = scrolledtext.ScrolledText(afternoon_frame, wrap=tk.WORD, height=8, width=40)
        self.afternoon_stations_text.grid(row=0, column=0, sticky="nsew")
        # Value will be set by load_configuration

        stations_frame.columnconfigure(0, weight=1)
        stations_frame.columnconfigure(1, weight=1)
        stations_frame.rowconfigure(0, weight=1)

        # --- Log Widgets (Needed for load_configuration logging) ---
        log_inner_frame = tk.Frame(self.log_frame)
        log_inner_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tk.Label(log_inner_frame, text="Logs:", font=self.bold_font).pack(anchor="w")
        self.log_area = scrolledtext.ScrolledText(log_inner_frame, wrap=tk.WORD, height=15, state=tk.DISABLED) # Start disabled
        self.log_area.pack(fill=tk.BOTH, expand=True, pady=(0,5))

        # --- Load Configuration ---
        self.load_configuration() # Try loading saved config before setting defaults

        # --- Control Widgets ---
        controls_inner_frame = tk.Frame(self.controls_frame)
        controls_inner_frame.pack(pady=5)

        self.start_button = tk.Button(controls_inner_frame, text="Start Tracking", command=self.start_tracking, width=15, height=2, bg="#4CAF50", fg="white", font=self.bold_font)
        self.start_button.grid(row=0, column=0, padx=10)

        self.stop_button = tk.Button(controls_inner_frame, text="Stop Tracking", command=self.stop_tracking, width=15, height=2, bg="#f44336", fg="white", state=tk.DISABLED, font=self.bold_font)
        self.stop_button.grid(row=0, column=1, padx=10)

        # Added Save Button
        self.save_button = tk.Button(controls_inner_frame, text="Save Config", command=self.save_configuration, width=12, height=2)
        self.save_button.grid(row=0, column=2, padx=10)

        self.status_label = tk.Label(controls_inner_frame, text="Status: Idle", fg="blue", width=35, anchor="w") # Adjusted width slightly
        self.status_label.grid(row=0, column=3, padx=15, sticky="w") # Adjusted column


        # --- Start processing the queue ---
        self.master.after(100, self.process_queue) # Check queue every 100ms

        # --- Handle window close ---
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)


    def log_message(self, message, level="INFO"):
        """Appends a message to the log area."""
        # Ensure log_area exists before trying to write (during early init)
        if not hasattr(self, 'log_area') or not self.log_area:
            print(f"[PRE-LOG] {level}: {message}") # Fallback print
            return

        timestamp = time.strftime('%H:%M:%S')
        # Changed format to put timestamp at the end
        formatted_message = f"[{level}] {message} [{timestamp}]\n"

        try:
            self.log_area.config(state=tk.NORMAL) # Enable writing
            self.log_area.insert(tk.END, formatted_message)
            self.log_area.see(tk.END) # Scroll to the end
            self.log_area.config(state=tk.DISABLED) # Disable writing
        except tk.TclError:
            # Handle case where the widget might be destroyed during shutdown
            print(f"[LOG-ERR] {level}: {message}")


    def update_status(self, status_text, color="blue"):
        """Updates the status label (excluding timer updates)."""
        if self.timer_update_id:
            self.master.after_cancel(self.timer_update_id)
            self.timer_update_id = None
        self.status_label.config(text=f"Status: {status_text}", fg=color)

    def get_station_ids_from_text(self, text_widget):
        """Extracts non-empty lines from a text widget as station IDs."""
        raw_text = text_widget.get("1.0", tk.END)
        ids = [line.strip() for line in raw_text.splitlines() if line.strip()]
        return ids

    # --- NEW METHOD ---
    def load_configuration(self):
        """Loads configuration from CONFIG_FILENAME if it exists."""
        loaded_config = {}
        config_path = os.path.join(os.path.dirname(__file__), CONFIG_FILENAME) # Path relative to script

        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    loaded_config = json.load(f)
                self.log_message(f"Configuration loaded from {config_path}", "INFO")
            except (json.JSONDecodeError, IOError) as e:
                self.log_message(f"Error loading {config_path}: {e}. Using defaults.", "ERROR")
                # Use messagebox only if GUI is fully initialized
                if self.master.winfo_exists():
                     messagebox.showerror("Config Load Error", f"Could not load configuration file '{CONFIG_FILENAME}'.\nError: {e}\n\nUsing default settings.")
            except Exception as e: # Catch other potential errors
                self.log_message(f"Unexpected error loading {config_path}: {e}", "ERROR")
                if self.master.winfo_exists():
                    messagebox.showerror("Config Load Error", f"An unexpected error occurred while loading '{CONFIG_FILENAME}'.\nError: {e}\n\nUsing default settings.")
        else:
            self.log_message(f"Configuration file '{CONFIG_FILENAME}' not found in script directory. Using defaults.", "INFO")

        # Populate fields - Use loaded value OR default if key missing/load failed
        # Ensure widgets exist before accessing them
        if hasattr(self, 'pushover_token_entry'):
            self.pushover_token_entry.delete(0, tk.END)
            self.pushover_token_entry.insert(0, loaded_config.get("pushover_token"))

        if hasattr(self, 'pushover_user_key_entry'):
            self.pushover_user_key_entry.delete(0, tk.END)
            self.pushover_user_key_entry.insert(0, loaded_config.get("pushover_user_key"))

        if hasattr(self, 'morning_stations_text'):
            self.morning_stations_text.delete("1.0", tk.END)
            morning_ids = loaded_config.get("morning_station_ids")
            self.morning_stations_text.insert(tk.END, "\n".join(morning_ids))

        if hasattr(self, 'afternoon_stations_text'):
            self.afternoon_stations_text.delete("1.0", tk.END)
            afternoon_ids = loaded_config.get("afternoon_station_ids")
            self.afternoon_stations_text.insert(tk.END, "\n".join(afternoon_ids))

    # --- NEW METHOD ---
    def save_configuration(self):
        """Saves the current configuration to CONFIG_FILENAME."""
        config_data = {
            "pushover_token": self.pushover_token_entry.get().strip(),
            "pushover_user_key": self.pushover_user_key_entry.get().strip(),
            "morning_station_ids": self.get_station_ids_from_text(self.morning_stations_text),
            "afternoon_station_ids": self.get_station_ids_from_text(self.afternoon_stations_text)
        }
        config_path = os.path.join(os.path.dirname(__file__), CONFIG_FILENAME) # Path relative to script

        try:
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=4)
            self.log_message(f"Configuration saved to {config_path}", "INFO")
            messagebox.showinfo("Config Saved", f"Configuration successfully saved to:\n{config_path}")
        except IOError as e:
            self.log_message(f"Error saving configuration to {config_path}: {e}", "ERROR")
            messagebox.showerror("Config Save Error", f"Could not save configuration file '{CONFIG_FILENAME}'.\nError: {e}")
        except Exception as e: # Catch other potential errors
            self.log_message(f"Unexpected error saving {config_path}: {e}", "ERROR")
            messagebox.showerror("Config Save Error", f"An unexpected error occurred while saving '{CONFIG_FILENAME}'.\nError: {e}")


    def start_tracking(self):
        """Starts the tracking process in a separate thread."""
        if self.tracking_active:
            messagebox.showwarning("Already Running", "Tracking is already active.")
            return

        # Read current values from GUI for this run
        self.pushover_token = self.pushover_token_entry.get().strip()
        self.pushover_user_key = self.pushover_user_key_entry.get().strip()

        if not self.pushover_token or self.pushover_token == "YOUR_APP_API_TOKEN_HERE" or \
           not self.pushover_user_key or self.pushover_user_key == "YOUR_USER_KEY_HERE":
             # Check against default values stored in the entry after loading
             default_token_in_entry = self.pushover_token_entry.get().strip() == DEFAULT_PUSHOVER_TOKEN
             default_user_in_entry = self.pushover_user_key_entry.get().strip() == DEFAULT_PUSHOVER_USER_KEY
             if default_token_in_entry or default_user_in_entry:
                if not messagebox.askyesno("Pushover Warning", "Pushover credentials seem missing or are defaults. Notifications will likely fail. Continue anyway?"):
                    return
             # Allow empty keys if user explicitly cleared them and proceeded

        # --- Determine which stations to track based on current time ---
        current_hour = datetime.datetime.now().hour
        morning_ids = self.get_station_ids_from_text(self.morning_stations_text)
        afternoon_ids = self.get_station_ids_from_text(self.afternoon_stations_text)

        mode = None
        if MORNING_START_HOUR <= current_hour < MORNING_END_HOUR:
            if not morning_ids:
                 messagebox.showerror("Error", "Morning time window, but no morning station IDs provided.")
                 return
            self.current_station_ids_to_track = morning_ids
            mode = "Morning"
        elif AFTERNOON_START_HOUR <= current_hour < AFTERNOON_END_HOUR:
            if not afternoon_ids:
                 messagebox.showerror("Error", "Afternoon time window, but no afternoon station IDs provided.")
                 return
            self.current_station_ids_to_track = afternoon_ids
            mode = "Afternoon"
        else:
            messagebox.showinfo("Outside Window", f"Current hour ({current_hour}) is outside the defined tracking windows ({MORNING_START_HOUR:02d}-{MORNING_END_HOUR:02d}, {AFTERNOON_START_HOUR:02d}-{AFTERNOON_END_HOUR:02d}). Tracking will not start.")
            return

        # --- Reset state and start tracking ---
        self.log_message(f"--- Starting Tracking ({mode} Mode) ---")
        self.log_message(f"Tracking {len(self.current_station_ids_to_track)} stations for {RUN_DURATION_MINUTES} minutes.")
        self.tracking_active = True
        self.stop_event.clear() # Ensure stop flag is reset
        self.station_names = None # Reset station names
        self.previous_ebike_status = {} # Reset status
        self.start_time = time.time()
        self.end_time = self.start_time + self.run_duration_seconds
        self.tracking_mode = mode

        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.save_button.config(state=tk.DISABLED) # Disable save while running
        self.update_countdown_timer()

        # Start the background thread
        self.tracking_thread = threading.Thread(target=self.tracking_thread_worker, daemon=True) # daemon=True allows closing app even if thread hangs
        self.tracking_thread.start()


    def stop_tracking(self, reason="Manually Stopped"):
        """Signals the tracking thread to stop."""
        if not self.tracking_active:
            return

        self.log_message(f"--- {reason} ---")
        self.stop_event.set() # Signal the thread to stop
        self.tracking_active = False
        self.tracking_mode = None
        self.end_time = None

        if self.timer_update_id:
            self.master.after_cancel(self.timer_update_id)
            self.timer_update_id = None

        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.save_button.config(state=tk.NORMAL) # Re-enable save button
        self.update_status(reason, "red")

    def update_countdown_timer(self):
        """Updates the status label with the remaining time."""
        if not self.tracking_active or self.end_time is None:
            self.timer_update_id = None
            return

        remaining_seconds = self.end_time - time.time()

        if remaining_seconds > 0:
            mins, secs = divmod(int(remaining_seconds), 60)
            time_str = f"{mins:02d}:{secs:02d} left"
            status_text = f"Status: Running ({self.tracking_mode} Mode) - {time_str}"
            self.status_label.config(text=status_text, fg="darkgreen")
            self.timer_update_id = self.master.after(1000, self.update_countdown_timer)
        else:
            # Timer reached zero, but let the thread handle the actual stop logic
            if self.tracking_active:
                 self.status_label.config(text=f"Status: Running ({self.tracking_mode} Mode) - 00:00 left", fg="darkgreen")
            self.timer_update_id = None


    def tracking_thread_worker(self):
        """The function that runs in the background thread."""
        try:
            self.result_queue.put(("log", "Fetching station information for names..."))
            self.station_names = self._get_station_name_map_thread()
            if self.station_names is None:
                 self.result_queue.put(("log", "Could not fetch station names. Stopping.", "ERROR"))
                 self.result_queue.put(("stop", "Error: Failed to get station names"))
                 return

            for station_id in self.current_station_ids_to_track:
                if station_id not in self.previous_ebike_status:
                    self.previous_ebike_status[station_id] = False
            self.result_queue.put(("log", "Station names fetched. Initializing e-bike status tracking."))


            while not self.stop_event.is_set():
                loop_start_time = time.time()

                # Check runtime limit FIRST
                elapsed_time = loop_start_time - self.start_time
                if elapsed_time >= self.run_duration_seconds: # Use >= for safety
                    self.result_queue.put(("log", f"Runtime limit ({RUN_DURATION_MINUTES} minutes) reached."))
                    self.result_queue.put(("stop", "Runtime Ended"))
                    break # Exit loop immediately

                # --- Fetch and Process Status ---
                try:
                    status_url = STATION_STATUS_URL
                    response = requests.get(status_url, timeout=20)
                    response.raise_for_status()
                    stations_status_data = response.json()["data"]["stations"]
                    stations_status_dict = {station['station_id']: station for station in stations_status_data}

                    current_log_lines = [f"\n--- Station E-Bike Status ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---"]
                    notification_needed = False
                    status_lines_for_notification = []
                    current_ebike_status = {}
                    triggering_station_names = []

                    for station_id in self.current_station_ids_to_track:
                        station_status = stations_status_dict.get(station_id)
                        # Use previously fetched station_names map
                        station_name = self.station_names.get(station_id, f"Unknown ({station_id[:6]}...)")

                        if station_status:
                            try:
                                total = int(station_status.get("num_bikes_available", 0))
                                ebikes = int(station_status.get("num_ebikes_available", 0))
                                docks = int(station_status.get("num_docks_available", 0))
                            except (ValueError, TypeError):
                                current_log_lines.append(f"Warning: Invalid data types for station {station_name} ({station_id}). Assuming 0 bikes.")
                                total, ebikes, docks = 0, 0, 0

                            has_ebikes_now = ebikes > 0
                            current_ebike_status[station_id] = has_ebikes_now
                            classic_bikes = max(0, total - ebikes)

                            log_line = f"Station: {station_name}\n" \
                                       f"  Classic bikes: {classic_bikes}\n" \
                                       f"  Electric bikes: {ebikes}\n" \
                                       f"  Open docks: {docks}\n" \
                                       f"-------------------------"
                            current_log_lines.append(log_line)
                            status_lines_for_notification.append(f"{station_name}: {ebikes} E, {classic_bikes} C, {docks} D")

                            # Check against previous status for *this* station
                            had_ebikes_before = self.previous_ebike_status.get(station_id, False)
                            if has_ebikes_now and not had_ebikes_before:
                                notification_needed = True
                                if station_name not in triggering_station_names:
                                    triggering_station_names.append(station_name)
                                current_log_lines.append(f"*** E-bike detected at {station_name}! (Will include in summary notification) ***")

                        else: # Station ID tracked but not found in current status feed
                            log_line = f"Station: {station_name}\n" \
                                       f"  Status not currently available in API feed.\n" \
                                       f"-------------------------"
                            current_log_lines.append(log_line)
                            status_lines_for_notification.append(f"{station_name}: Status N/A")
                            current_ebike_status[station_id] = False # Assume no e-bikes if status missing

                    # Send log update for this cycle
                    self.result_queue.put(("log", "\n".join(current_log_lines)))

                    # Send notification if needed (after processing all stations for this cycle)
                    if notification_needed:
                        notification_title = f"E-Bike Alert!"
                        notification_message = f"E-bike(s) detected at {', '.join(triggering_station_names)}!\n\nFull Status:\n" + "\n".join(status_lines_for_notification)
                        self.result_queue.put(("log", f"--- Sending Pushover Notification (Triggered by: {', '.join(triggering_station_names)}) ---", "IMPORTANT"))
                        # Send Pushover in this thread
                        success = self._send_pushover_notification_thread(notification_message, title=notification_title)
                        if success:
                             self.result_queue.put(("log", f"Pushover notification sent successfully."))
                        else:
                             self.result_queue.put(("log", f"Failed to send Pushover notification.", "ERROR"))

                    # Update the master previous status dict for the next cycle
                    self.previous_ebike_status = current_ebike_status.copy()

                    # Clean up stale entries (should not happen if current_station_ids_to_track is static during run)
                    stale_ids = [s_id for s_id in self.previous_ebike_status if s_id not in self.current_station_ids_to_track]
                    for s_id in stale_ids:
                        del self.previous_ebike_status[s_id]
                        self.result_queue.put(("log", f"Removed stale station ID {s_id} from tracking status.", "DEBUG"))


                except requests.exceptions.Timeout:
                    self.result_queue.put(("log", f"Network Error: Request timed out while fetching status.", "ERROR"))
                except requests.exceptions.RequestException as e:
                    self.result_queue.put(("log", f"Network/Request Error fetching status: {e}", "ERROR"))
                except (json.JSONDecodeError, KeyError) as e:
                    self.result_queue.put(("log", f"Error processing station status data: {e}", "ERROR"))
                except Exception as e: # Catch unexpected errors in loop
                     self.result_queue.put(("log", f"An unexpected error occurred in tracking loop: {e}", "ERROR"))


                # --- Wait before next check ---
                # Calculate wait time, ensuring it's not negative
                wait_actual = max(0, CHECK_INTERVAL_SECONDS - (time.time() - loop_start_time))
                # Use stop_event.wait for interruptible sleep
                # This will wait for 'wait_actual' seconds OR until stop_event is set
                interrupted = self.stop_event.wait(timeout=wait_actual)
                if interrupted: # If stop_event was set during wait
                    break # Exit the loop immediately


        except Exception as e: # Catch errors happening outside the main loop but inside the thread
            self.result_queue.put(("log", f"Critical error in tracking thread: {e}", "ERROR"))
            self.result_queue.put(("stop", "Thread Error"))

        # Final message only if thread finishes *without* being stopped by event
        if not self.stop_event.is_set():
             self.result_queue.put(("log", "--- Tracking Thread Finished Naturally (Should have been stopped by timer/manual) ---", "WARNING"))


    def _get_station_name_map_thread(self):
        """Fetches station information (intended for background thread)."""
        try:
            response = requests.get(STATION_INFO_URL, timeout=15)
            response.raise_for_status()
            stations_info = response.json()["data"]["stations"]
            name_map = {station['station_id']: station['name'] for station in stations_info}
            return name_map
        except requests.exceptions.RequestException as e:
            self.result_queue.put(("log", f"Error fetching station information: {e}", "ERROR"))
            return None
        except (json.JSONDecodeError, KeyError) as e: # More specific JSON errors
            self.result_queue.put(("log", f"Error processing station information JSON: {e}", "ERROR"))
            return None
        except Exception as e: # Catch other unexpected errors
            self.result_queue.put(("log", f"Unexpected error fetching station names: {e}", "ERROR"))
            return None


    def _send_pushover_notification_thread(self, message, title="Bluebikes E-Bike Alert"):
        """Sends a notification message using Pushover (intended for background thread)."""
        # Use the token/key read at the start of tracking
        if not self.pushover_user_key or not self.pushover_token:
            self.result_queue.put(("log", "Pushover credentials missing for this run. Skipping notification.", "WARNING"))
            return False

        payload = {
            "token": self.pushover_token,
            "user": self.pushover_user_key,
            "message": message,
            "title": title
            # Add other parameters like sound, priority if needed
            # "sound": "pushover",
            # "priority": 0,
        }
        headers = {"Content-type": "application/x-www-form-urlencoded"}

        try:
            response = requests.post(PUSHOVER_API_URL, data=payload, headers=headers, timeout=15)
            response.raise_for_status()
            # Success will be logged by the caller via the queue
            return True
        except requests.exceptions.RequestException as e:
            # Log failure via queue
            error_msg = f"Error sending Pushover notification: {e}"
            if e.response is not None:
                 # Include status code and snippet of response text for debugging
                 error_msg += f" (Status: {e.response.status_code}, Response: {e.response.text[:100]}...)"
            self.result_queue.put(("log", error_msg, "ERROR"))
            return False
        except Exception as e: # Catch other unexpected errors
             self.result_queue.put(("log", f"An unexpected error occurred sending Pushover notification: {e}", "ERROR"))
             return False

    def process_queue(self):
        """Processes messages put in the queue by the background thread."""
        try:
            while True: # Process all waiting messages in the queue
                msg_type, *payload = self.result_queue.get_nowait()

                if msg_type == "log":
                    message, level = payload[0], payload[1] if len(payload) > 1 else "INFO"
                    self.log_message(message, level=level)
                elif msg_type == "stop":
                    reason = payload[0] if payload else "Stopped by Thread"
                    # Only call stop_tracking if it's currently considered active
                    # This prevents race conditions or double-stops
                    if self.tracking_active:
                        self.stop_tracking(reason=reason)
                        # Optional: Auto-close logic (kept from previous version)
                        # if reason == "Runtime Ended":
                        #    self.log_message("Timer ended. Closing application.", "INFO")
                        #    self.master.after(100, self.master.destroy)
                        #    return # Exit processing as the window will close

        except queue.Empty:
            # No messages left in the queue for now
            pass
        except Exception as e:
             # Catch potential errors during queue processing itself
             self.log_message(f"Error processing queue: {e}", "ERROR")
        finally:
            # Reschedule processing ONLY if the window still exists
            # This prevents errors after the window is destroyed
            if self.master.winfo_exists():
                 self.master.after(100, self.process_queue)


    def on_closing(self):
        """Handles the window close event."""
        if self.tracking_active:
            if messagebox.askyesno("Quit", "Tracking is active. Are you sure you want to quit? This will stop the tracking."):
                self.stop_tracking("Application Closed")
                # Give a very short time for the stop signal to potentially be processed
                # Note: Daemon thread might still be running briefly but should exit eventually
                time.sleep(0.1)
                self.master.destroy()
            else:
                return # Don't close if user clicks No
        else:
            self.master.destroy() # Close immediately if not tracking

    def check_and_close_if_not_tracking(self):
        """Checks if tracking started; closes the app if not."""
        # Check if tracking is still not active after the delay
        if not self.tracking_active:
            print("Tracking did not start within the time limit. Closing application.") # Print to console as GUI might close immediately
            self.master.destroy() # Close the Tkinter window

# --- Main Execution ---
if __name__ == "__main__":
    # Set script path context for finding config file relative to script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir) # Change working directory to script's directory

    root = tk.Tk()
    app = BluebikesTrackerApp(root)

    # --- Automatically start tracking ---
    # Schedule start_tracking to run shortly after the main loop starts
    root.after(100, app.start_tracking)

    # --- Schedule check to close if tracking doesn't start ---
    # Check after 10 seconds (10000 milliseconds)
    root.after(10000, app.check_and_close_if_not_tracking)

    root.mainloop()