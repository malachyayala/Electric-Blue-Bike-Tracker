# Bluebikes E-Bike Tracker

## Description

This Python application provides a graphical user interface (GUI) to monitor specific Bluebikes stations in the Boston area, primarily focusing on tracking the availability of e-bikes. It checks station statuses at regular intervals during predefined morning and afternoon time windows. When an e-bike becomes available at a tracked station where none were previously detected, the application sends a notification via the Pushover service. It also includes a utility script to help users find the necessary station IDs.

## Features

* **GUI Interface:** Built with Tkinter for easy configuration and monitoring.
* **Scheduled Tracking:** Monitors stations only during specific morning (8 AM - 12 PM) and afternoon (4 PM - 7 PM) windows.
* **Real-time Data:** Fetches up-to-date station information and status directly from the official Bluebikes GBFS (General Bikeshare Feed Specification) API.
* **E-Bike Detection:** Specifically looks for the appearance of `num_ebikes_available` at tracked stations.
* **Pushover Notifications:** Sends instant alerts to your devices via Pushover when a *new* e-bike is detected at a monitored station.
* **Configurable:**
    * Set your Pushover API Token and User Key.
    * Define separate lists of station IDs to monitor during morning and afternoon windows.
* **Configuration Persistence:** Saves your Pushover keys and station lists to a `myconfig.json` file, automatically loading them on startup.
* **Activity Logging:** Displays status updates, checks, detected e-bikes, and potential errors within the application's log window.
* **Automatic Operation:**
    * Attempts to start tracking automatically if launched within a defined time window.
    * Runs for a configurable duration (default 30 minutes) after starting.
* **Station ID Finder:** Includes a separate command-line script (`station_id_finder.py`) to search for station names and retrieve their corresponding IDs.

## Requirements

* Python 3
* `requests` library (install via `pip install requests`)
* A Pushover account and API credentials (Application Token and User Key).

## Setup and Configuration

1.  **Install Requirements:**
    ```bash
    pip install requests
    ```
2.  **Get Pushover Credentials:**
    * Log in to your Pushover account.
    * Register an application to get an **API Token/Key**.
    * Find your **User Key** on your Pushover dashboard.
3.  **Find Station IDs:**
    * Run the `station_id_finder.py` script:
        ```bash
        python station_id_finder.py
        ```
    * Enter parts of station names when prompted (e.g., "South Station", "MIT") to find the stations you want to track.
    * Note down the `Station ID` for each desired station.
4.  **Configure the Application:**
    * **Option A (Recommended): Run the App First:**
        * Launch the main application (`blue_bike_tracker.py`).
        * Enter your Pushover API Token and User Key into the respective fields in the GUI.
        * Paste the station IDs you found into the "Morning Stations" and "Afternoon Stations" text boxes, one ID per line.
        * Click the "Save Config" button. This will create/update the `myconfig.json` file.
    * **Option B (Manual Edit):**
        * Open the `myconfig.json` file (or copy `config.json` to `myconfig.json` if it doesn't exist).
        * Replace `"PUSHOVER_TOKEN"` and `"PUSHOVER_USER_KEY"` with your actual Pushover credentials.
        * Add the station IDs you collected into the `morning_station_ids` and `afternoon_station_ids` lists.
        ```json
        {
            "pushover_token": "YOUR_PUSHOVER_APP_API_TOKEN",
            "pushover_user_key": "YOUR_PUSHOVER_USER_KEY",
            "morning_station_ids": [
                "station_id_1",
                "station_id_2"
            ],
            "afternoon_station_ids": [
                "station_id_3",
                "station_id_4"
            ]
        }
        ```

## Usage

1.  **Run the Tracker:**
    ```bash
    python blue_bike_tracker.py
    ```
2.  **GUI Overview:**
    * **Pushover Credentials:** Fields to enter/view your API and User keys.
    * **Station ID Lists:** Text areas for morning and afternoon station IDs.
    * **Start Tracking:** Manually starts the tracking process if within a valid time window. The script also attempts to start automatically on launch.
    * **Stop Tracking:** Manually stops the current tracking cycle.
    * **Save Config:** Saves the current Pushover keys and station IDs from the GUI to `myconfig.json`.
    * **Status Label:** Shows the current state (Idle, Running, Stopped, Error) and remaining time when running.
    * **Logs:** Displays detailed information about checks, API calls, e-bike detections, notifications sent, and errors.
3.  **Operation:**
    * The application checks the Bluebikes API every `CHECK_INTERVAL_SECONDS` (default 15 seconds).
    * If started, it runs for `RUN_DURATION_MINUTES` (default 30 minutes) before stopping automatically.
    * It determines whether to use the morning or afternoon station list based on the current time when tracking starts.
    * If an e-bike appears at a station that had zero e-bikes in the previous check, a Pushover notification is triggered for that station.

## How It Works

The application uses Python's `tkinter` library for the GUI. A background thread (`threading`) is used to perform the network requests and tracking logic without freezing the interface.

1.  **Initialization:** Loads configuration from `myconfig.json`.
2.  **Start:** When tracking starts (manually or automatically), it determines the correct time window (Morning/Afternoon) and corresponding station list. It fetches the station names corresponding to the IDs for user-friendly logging.
3.  **Tracking Loop:**
    * Checks if the run duration has expired.
    * Fetches the current `station_status.json` from the Bluebikes API.
    * For each tracked station ID, it extracts the number of available e-bikes (`num_ebikes_available`).
    * It compares the current e-bike count to the count from the previous check for that station.
    * If the count was 0 and is now > 0, it flags that a notification is needed.
    * Logs the status of all tracked stations.
    * Sends a single Pushover notification summarizing all stations where *new* e-bikes were detected during that check cycle.
    * Updates the stored e-bike status for the next comparison.
    * Waits for the defined interval before the next check.
4.  **Communication:** Uses a `queue.Queue` to safely pass information (log messages, stop signals) from the background thread to the main GUI thread.
5.  **Stop:** Tracking stops when the duration expires, the user clicks "Stop Tracking", the application is closed, or a critical error occurs.

## Files

* `blue_bike_tracker.py`: The main application script containing the GUI and tracking logic.
* `station_id_finder.py`: A utility script to look up Bluebikes station IDs by name.
* `config.json`: A template configuration file showing the expected structure. Not directly used if `myconfig.json` exists.

## Dependencies

* **requests:** For making HTTP requests to the Bluebikes and Pushover APIs.
* **tkinter:** (Usually included with Python) For the graphical user interface.