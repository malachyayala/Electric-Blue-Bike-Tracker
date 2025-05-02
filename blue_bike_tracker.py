import tkinter as tk
from tkinter import scrolledtext, messagebox, font as tkFont
import requests
import time
import json
import datetime
import threading # To run blocking tasks without freezing the GUI
import queue      # To communicate between threads

# --- Default Configuration (will be loaded into GUI) ---
DEFAULT_MORNING_STATION_IDS = [
    'bd1755dc-f26c-420e-85b3-fd025d0b5445', # Forsyth St at Huntington Ave
    '2438d052-2cd6-4fba-83c9-39f46cb59398', # Parker St at Huntington Ave
    'f834662c-0de8-11e7-991c-3863bb43a7d0', # NEU Parking Lot
    'f83483f3-0de8-11e7-991c-3863bb43a7d0', # Christian Science Plaza
    'f8350be5-0de8-11e7-991c-3863bb43a7d0', # Wentworth Institute of Technology
    '5018e851-f2f3-4e18-9914-c316bbcc2c3d', # Huntington Ave at Mass Art
]

DEFAULT_AFTERNOON_STATION_IDS = [
    "f834a67b-0de8-11e7-991c-3863bb43a7d0", # HLS @ Mass Ave / Jarvis St
    'f834ba08-0de8-11e7-991c-3863bb43a7d0', # Harvard University / SEAS
    'f834b652-0de8-11e7-991c-3863bb43a7d0', # Harvard University / Radcliffe Quadrangle
    '800bde2c-51df-497c-ac2d-bc3a8c00c164', # Church St
    'f83497b9-0de8-11e7-991c-3863bb43a7d0', # Harvard Square at Dunster
    'f8349745-0de8-11e7-991c-3863bb43a7d0', # Harvard Square at Brattle St
]

# --- Default Pushover (Replace with yours or enter in GUI) ---
DEFAULT_PUSHOVER_TOKEN = "ac8yskdsnj3s1u6q41eptud4nncysj" # Replace if desired
DEFAULT_PUSHOVER_USER_KEY = "ujpidngha6jfp3ottrcfzkbxxw7j34"     # Replace if desired
PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"

# --- Time Window Defaults (can be adjusted here) ---
MORNING_START_HOUR = 8
MORNING_END_HOUR = 12
AFTERNOON_START_HOUR = 16
AFTERNOON_END_HOUR = 19
CHECK_INTERVAL_SECONDS = 30 # How often to check status
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
        self.pushover_token_entry.insert(0, DEFAULT_PUSHOVER_TOKEN)

        tk.Label(pushover_frame, text="User Key:").grid(row=1, column=0, sticky="w", padx=2)
        self.pushover_user_key_entry = tk.Entry(pushover_frame, width=40)
        self.pushover_user_key_entry.grid(row=1, column=1, sticky="ew", padx=2)
        self.pushover_user_key_entry.insert(0, DEFAULT_PUSHOVER_USER_KEY)

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
        self.morning_stations_text.insert(tk.END, "\n".join(DEFAULT_MORNING_STATION_IDS))

        # Afternoon Stations
        afternoon_frame = tk.LabelFrame(stations_frame, text=f"Afternoon Stations ({AFTERNOON_START_HOUR:02d}:00 - {AFTERNOON_END_HOUR:02d}:00)", padx=5, pady=5, font=self.bold_font)
        afternoon_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        afternoon_frame.rowconfigure(0, weight=1)
        afternoon_frame.columnconfigure(0, weight=1)
        self.afternoon_stations_text = scrolledtext.ScrolledText(afternoon_frame, wrap=tk.WORD, height=8, width=40)
        self.afternoon_stations_text.grid(row=0, column=0, sticky="nsew")
        self.afternoon_stations_text.insert(tk.END, "\n".join(DEFAULT_AFTERNOON_STATION_IDS))

        stations_frame.columnconfigure(0, weight=1)
        stations_frame.columnconfigure(1, weight=1)
        stations_frame.rowconfigure(0, weight=1)

        # --- Control Widgets ---
        controls_inner_frame = tk.Frame(self.controls_frame)
        controls_inner_frame.pack(pady=5)

        self.start_button = tk.Button(controls_inner_frame, text="Start Tracking", command=self.start_tracking, width=15, height=2, bg="#4CAF50", fg="white", font=self.bold_font)
        self.start_button.grid(row=0, column=0, padx=10)

        self.stop_button = tk.Button(controls_inner_frame, text="Stop Tracking", command=self.stop_tracking, width=15, height=2, bg="#f44336", fg="white", state=tk.DISABLED, font=self.bold_font)
        self.stop_button.grid(row=0, column=1, padx=10)

        self.status_label = tk.Label(controls_inner_frame, text="Status: Idle", fg="blue", width=40, anchor="w")
        self.status_label.grid(row=0, column=2, padx=15, sticky="w")

        # --- Log Widgets ---
        log_inner_frame = tk.Frame(self.log_frame)
        log_inner_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tk.Label(log_inner_frame, text="Logs:", font=self.bold_font).pack(anchor="w")
        self.log_area = scrolledtext.ScrolledText(log_inner_frame, wrap=tk.WORD, height=15, state=tk.DISABLED) # Start disabled
        self.log_area.pack(fill=tk.BOTH, expand=True, pady=(0,5))

        # --- Start processing the queue ---
        self.master.after(100, self.process_queue) # Check queue every 100ms

        # --- Handle window close ---
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)


    def log_message(self, message, level="INFO"):
        """Appends a message to the log area."""
        timestamp = time.strftime('%H:%M:%S')
        formatted_message = f"[{timestamp} {level}] {message}\n"

        self.log_area.config(state=tk.NORMAL) # Enable writing
        self.log_area.insert(tk.END, formatted_message)
        self.log_area.see(tk.END) # Scroll to the end
        self.log_area.config(state=tk.DISABLED) # Disable writing

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

    def start_tracking(self):
        """Starts the tracking process in a separate thread."""
        if self.tracking_active:
            messagebox.showwarning("Already Running", "Tracking is already active.")
            return

        self.pushover_token = self.pushover_token_entry.get().strip()
        self.pushover_user_key = self.pushover_user_key_entry.get().strip()

        if not self.pushover_token or self.pushover_token == "YOUR_APP_API_TOKEN_HERE" or \
           not self.pushover_user_key or self.pushover_user_key == "YOUR_USER_KEY_HERE":
            if not messagebox.askyesno("Pushover Warning", "Pushover credentials seem missing or are defaults. Notifications will likely fail. Continue anyway?"):
                return

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

                elapsed_time = loop_start_time - self.start_time
                if elapsed_time > self.run_duration_seconds:
                    self.result_queue.put(("log", f"Runtime limit ({RUN_DURATION_MINUTES} minutes) reached."))
                    self.result_queue.put(("stop", "Runtime Ended"))
                    break

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

                            had_ebikes_before = self.previous_ebike_status.get(station_id, False)
                            if has_ebikes_now and not had_ebikes_before:
                                notification_needed = True
                                if station_name not in triggering_station_names:
                                    triggering_station_names.append(station_name)
                                current_log_lines.append(f"*** E-bike detected at {station_name}! (Will include in summary notification) ***")

                        else:
                            log_line = f"Station: {station_name}\n" \
                                       f"  Status not currently available in API feed.\n" \
                                       f"-------------------------"
                            current_log_lines.append(log_line)
                            status_lines_for_notification.append(f"{station_name}: Status N/A")
                            current_ebike_status[station_id] = False

                    self.result_queue.put(("log", "\n".join(current_log_lines)))

                    if notification_needed:
                        notification_title = f"E-Bike Alert!"
                        notification_message = f"E-bike(s) detected at {', '.join(triggering_station_names)}!\n\nFull Status:\n" + "\n".join(status_lines_for_notification)
                        self.result_queue.put(("log", f"--- Sending Pushover Notification (Triggered by: {', '.join(triggering_station_names)}) ---", "IMPORTANT"))
                        success = self._send_pushover_notification_thread(notification_message, title=notification_title)
                        if success:
                             self.result_queue.put(("log", f"Pushover notification sent successfully."))
                        else:
                             self.result_queue.put(("log", f"Failed to send Pushover notification.", "ERROR"))


                    self.previous_ebike_status = current_ebike_status.copy()

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
                except Exception as e:
                     self.result_queue.put(("log", f"An unexpected error occurred in tracking loop: {e}", "ERROR"))


                wait_actual = max(0, CHECK_INTERVAL_SECONDS - (time.time() - loop_start_time))
                self.stop_event.wait(timeout=wait_actual)

        except Exception as e:
            self.result_queue.put(("log", f"Critical error in tracking thread: {e}", "ERROR"))
            self.result_queue.put(("stop", "Thread Error"))

        if not self.stop_event.is_set():
             self.result_queue.put(("log", "--- Tracking Thread Finished ---"))


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
        except (json.JSONDecodeError, KeyError) as e:
            self.result_queue.put(("log", f"Error processing station information: {e}", "ERROR"))
            return None
        except Exception as e:
            self.result_queue.put(("log", f"Unexpected error fetching station names: {e}", "ERROR"))
            return None


    def _send_pushover_notification_thread(self, message, title="Bluebikes E-Bike Alert"):
        """Sends a notification message using Pushover (intended for background thread)."""
        if not self.pushover_user_key or not self.pushover_token:
            self.result_queue.put(("log", "Pushover credentials missing. Skipping notification.", "WARNING"))
            return False

        payload = {
            "token": self.pushover_token,
            "user": self.pushover_user_key,
            "message": message,
            "title": title
        }
        headers = {"Content-type": "application/x-www-form-urlencoded"}

        try:
            response = requests.post(PUSHOVER_API_URL, data=payload, headers=headers, timeout=15)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            error_msg = f"Error sending Pushover notification: {e}"
            if e.response is not None:
                 error_msg += f" (Status: {e.response.status_code}, Response: {e.response.text[:100]}...)"
            self.result_queue.put(("log", error_msg, "ERROR"))
            return False
        except Exception as e:
             self.result_queue.put(("log", f"An unexpected error occurred sending Pushover notification: {e}", "ERROR"))
             return False

    def process_queue(self):
        """Processes messages put in the queue by the background thread."""
        try:
            while True:
                msg_type, *payload = self.result_queue.get_nowait()

                if msg_type == "log":
                    message, level = payload[0], payload[1] if len(payload) > 1 else "INFO"
                    self.log_message(message, level=level)
                elif msg_type == "stop":
                    reason = payload[0] if payload else "Stopped by Thread"
                    if self.tracking_active: # Check if tracking was active before stopping
                        self.stop_tracking(reason=reason)
                        # Check if the reason for stopping was the timer ending
                        if reason == "Runtime Ended":
                            self.log_message("Timer ended. Closing application.", "INFO")
                            # Give a brief moment for UI updates before destroying
                            self.master.after(100, self.master.destroy)
                            return # Exit processing as the window will close

        except queue.Empty:
            pass
        finally:
            # Ensure the after call is only scheduled if the window isn't being destroyed
            if self.master.winfo_exists():
                 self.master.after(100, self.process_queue)


    def on_closing(self):
        """Handles the window close event."""
        if self.tracking_active:
            if messagebox.askyesno("Quit", "Tracking is active. Are you sure you want to quit? This will stop the tracking."):
                self.stop_tracking("Application Closed")
                time.sleep(0.1)
                self.master.destroy()
            else:
                return
        else:
            self.master.destroy()

# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()
    app = BluebikesTrackerApp(root)
    root.mainloop()