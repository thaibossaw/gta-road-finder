import requests
import json
import os

class VehicleApi:
    def __init__(self, baseUrl='https://gta.vercel.app/api/vehicles'):
        if baseUrl.endswith('/'):
            baseUrl = baseUrl[:-1]
        self.baseUrl = baseUrl

        self.cache_file = 'vehicles_cache.json'
        self.image_folder = 'vehicle_images'
        os.makedirs(self.image_folder, exist_ok=True)  # Create the folder if it doesn't exist
        self.cache = self.load_cache()
        self.get_all()

    def _get(self, path: str):
        path = path.strip('/')
        full_path = f'{self.baseUrl}/{path}'
        res = requests.get(full_path)
        if not res.status_code == 200:
            raise Exception(f'Failed to get endpoint: {path}, HTTP {res.status_code}')
        return json.loads(res.content)

    def get_all(self):
        try:
            # Try fetching data from the API
            data = self._get('all')
            self.save_cache(data)  # Update the cache on successful fetch
            return data
        except Exception as e:
            print(f"Error fetching data from API: {e}")
            if self.cache:
                print("Using cached data instead.")
                return self.cache
            raise Exception("No cache available and API request failed.") from e

    def get_all_vehicle_names(self):
        """Returns a list of all vehicle names from the cache or API."""
        if self.cache is None:
            print("Cache is empty, fetching data from API...")
            self.cache = self.get_all()

        # Iterate through categories and vehicles to extract names
        vehicle_names = []
        for category, vehicles in self.cache.items():
            vehicle_names.extend(vehicles.keys())

        print(f"Retrieved {len(vehicle_names)} vehicle names.")
        print(vehicle_names)
        return vehicle_names
    

    def get_image_for_name(self, name: str):
        """Returns the local path to the front-quarter image of a vehicle."""
        if self.cache is None:
            print("Cache is empty, fetching data from API...")
            self.cache = self.get_all()

        for category, vehicles in self.cache.items():
            for vehicle_name, details in vehicles.items():
                if vehicle_name.lower() == name.lower():
                    images = details.get("images", {})
                    image_url = images.get('frontQuarter')

                    if not image_url:
                        print(f"No front-quarter image found for '{name}'.")
                        return None

                    # Define local image path
                    image_filename = f"{name.replace(' ', '_').lower()}.jpg"
                    image_path = os.path.join(self.image_folder, image_filename)

                    # Download and cache the image if not already cached
                    if not os.path.exists(image_path):
                        print(f"Downloading image for '{name}'...")
                        try:
                            response = requests.get(image_url)
                            response.raise_for_status()  # Raise error for HTTP issues
                            with open(image_path, 'wb') as f:
                                f.write(response.content)
                            print(f"Image for '{name}' saved to '{image_path}'.")
                        except Exception as e:
                            print(f"Failed to download image for '{name}': {e}")
                            return None
                    else:
                        print(f"Image for '{name}' is already cached at '{image_path}'.")

                    return image_path

        print(f"Vehicle with name '{name}' not found.")
        return None

    def load_cache(self):
        """Load cache from the JSON file."""
        print("Loading Cache...")
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading cache: {e}")
        return None

    def save_cache(self, data):
        """Save data to the JSON cache file."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=4)
            print("Cache updated successfully.")
        except Exception as e:
            print(f"Error saving cache: {e}")


if __name__ == '__main__':
    print(VehicleApi().get_image_for_name('adder'))