import requests

def get_weather(lat=22.5726, lon=88.3639, city="Kolkata"):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code"
    try:
        data = requests.get(url, timeout=5).json()
        temp = data["current"]["temperature_2m"]
        return f"It's currently {temp} degrees Celsius in {city}."
    except Exception:
        return "I couldn't fetch the weather right now."