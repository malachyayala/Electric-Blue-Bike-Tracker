import requests

# Download station information
url = "https://gbfs.bluebikes.com/gbfs/en/station_information.json"
response = requests.get(url)
stations = response.json()["data"]["stations"]

# Get input from user
query = input("Enter part of the station name to search: ").lower()

# Search for matches
matches = [s for s in stations if query in s["name"].lower()]

# Show results
if matches:
    print(f"\nFound {len(matches)} match(es):\n")
    for station in matches:
        print(f"Name: {station['name']}")
        print(f"Station ID: {station['station_id']}")
        print(f"Capacity: {station['capacity']}")
        print(f"Location: ({station['lat']}, {station['lon']})")
        print("-" * 40)
else:
    print("No stations found matching that name.")
