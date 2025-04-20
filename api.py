from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_caching import Cache
import requests
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app)

# Configure cache
cache = Cache(app, config={
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 300  # 5 minutes
})

# API configuration
API_KEY = 'use your key here'
GEOCODE_URL = "http://api.openweathermap.org/geo/1.0/direct"
REVERSE_GEOCODE_URL = "http://api.openweathermap.org/geo/1.0/reverse"
CURRENT_WEATHER_URL = "http://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "http://api.openweathermap.org/data/2.5/forecast"
AIR_POLLUTION_URL = "http://api.openweathermap.org/data/2.5/air_pollution"

@app.route('/')
def home():
    return app.send_static_file('pylink.html')

@app.route('/get_weather', methods=['GET', 'POST'])
def get_weather():
    try:
        if request.method == 'POST':
            data = request.get_json()
            city = data.get('city')
            
            if not city:
                return jsonify({'error': 'City name is required'}), 400
            
            geo_data = get_geocode_data(city)
            if not geo_data:
                return jsonify({'error': f'Could not find location for city: {city}'}), 404
                
            lat, lon = geo_data['lat'], geo_data['lon']
            location_info = {
                'city': geo_data.get('name', city),
                'country': geo_data.get('country', ''),
                'state': geo_data.get('state', ''),
                'coordinates': {'lat': lat, 'lon': lon}
            }
        else:  # GET request with coordinates
            lat = request.args.get('lat')
            lon = request.args.get('lon')
            
            if not lat or not lon:
                return jsonify({'error': 'Latitude and longitude are required'}), 400
                
            try:
                lat = float(lat)
                lon = float(lon)
            except ValueError:
                return jsonify({'error': 'Invalid coordinates'}), 400
                
            geo_data = get_reverse_geocode_data(lat, lon)
            location_info = {
                'city': geo_data.get('name', 'Current Location') if geo_data else 'Current Location',
                'country': geo_data.get('country', '') if geo_data else '',
                'state': geo_data.get('state', '') if geo_data else '',
                'coordinates': {'lat': lat, 'lon': lon}
            }
        
        current = fetch_current_weather(lat, lon)
        forecast = fetch_5day_forecast(lat, lon)
        air_quality = fetch_air_quality(lat, lon)
        
        return jsonify({
            'current': current,
            'forecast': forecast,
            'air_quality': air_quality,
            'location': location_info,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'Weather service unavailable', 'details': str(e)}), 503
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/get_hourly_forecast', methods=['GET'])
def get_hourly_forecast():
    try:
        lat = request.args.get('lat')
        lon = request.args.get('lon')
        
        if not lat or not lon:
            return jsonify({'error': 'Latitude and longitude are required'}), 400
            
        try:
            lat = float(lat)
            lon = float(lon)
        except ValueError:
            return jsonify({'error': 'Invalid coordinates'}), 400
            
        params = {
            'lat': lat,
            'lon': lon,
            'units': 'metric',
            'appid': API_KEY
        }
        
        response = requests.get(FORECAST_URL, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        return jsonify(data)
        
    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'Forecast service unavailable', 'details': str(e)}), 503
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

def get_geocode_data(city):
    city = city.strip()
    params = {
        'q': city,
        'limit': 10,  # Get more results to find the best match
        'appid': API_KEY
    }
    try:
        response = requests.get(GEOCODE_URL, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            print(f"No geocoding results for city: {city}")
            return None
            
        # Find the best match (exact city name match if possible)
        for result in data:
            if result.get('name', '').lower() == city.lower():
                return {
                    'name': result.get('name'),
                    'country': result.get('country', ''),
                    'state': result.get('state', ''),
                    'lat': result.get('lat'),
                    'lon': result.get('lon')
                }
                
        # Fallback to first result
        return {
            'name': data[0].get('name'),
            'country': data[0].get('country', ''),
            'state': data[0].get('state', ''),
            'lat': data[0].get('lat'),
            'lon': data[0].get('lon')
        }
        
    except requests.exceptions.RequestException as e:
        print(f"Geocoding error for city {city}: {str(e)}")
        return None
def get_reverse_geocode_data(lat, lon):
    params = {
        'lat': lat,
        'lon': lon,
        'limit': 10,  # Get multiple results to find the most accurate
        'appid': API_KEY
    }
    try:
        response = requests.get(REVERSE_GEOCODE_URL, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return None
            
        # Prioritize results with 'local_names' and higher accuracy
        for result in sorted(data, key=lambda x: -x.get('importance', 0)):
            # Skip administrative areas that might be too broad
            if result.get('local_names'):
                name = result['local_names'].get('en') or result.get('name')
                print(f"Reverse geocode selected: {name} (Type: {result.get('type')}, Importance: {result.get('importance')})")
                return {
                    'name': name,
                    'country': result.get('country', ''),
                    'state': result.get('state', '')
                }
        
        # Fallback to first result if no local names found
        return {
            'name': data[0].get('name'),
            'country': data[0].get('country', ''),
            'state': data[0].get('state', '')
        }
        
    except requests.exceptions.RequestException as e:
        print(f"Reverse geocoding error: {str(e)}")
        return None
def fetch_current_weather(lat, lon):
    params = {
        'lat': lat,
        'lon': lon,
        'units': 'metric',
        'appid': API_KEY
    }
    response = requests.get(CURRENT_WEATHER_URL, params=params, timeout=5)
    response.raise_for_status()
    data = response.json()
    
    return {
        'temp': round(data['main']['temp'], 1),
        'feels_like': round(data['main']['feels_like'], 1),
        'description': data['weather'][0]['description'].capitalize(),
        'icon': data['weather'][0]['icon'],
        'humidity': data['main']['humidity'],
        'wind': round(data['wind']['speed'] * 3.6, 1),  # Convert to km/h
        'pressure': data['main']['pressure'],
        'visibility': round(data.get('visibility', 0) / 1000, 1),  # Convert to km
        'sunrise': datetime.fromtimestamp(data['sys']['sunrise']).strftime('%H:%M'),
        'sunset': datetime.fromtimestamp(data['sys']['sunset']).strftime('%H:%M'),
        'observation_time': datetime.fromtimestamp(data['dt']).strftime('%H:%M UTC')
    }

def fetch_5day_forecast(lat, lon):
    params = {
        'lat': lat,
        'lon': lon,
        'units': 'metric',
        'cnt': 40,  # 5 days * 8 forecasts per day
        'appid': API_KEY
    }
    response = requests.get(FORECAST_URL, params=params, timeout=5)
    response.raise_for_status()
    data = response.json()
    
    # Group by day and get daily min/max
    daily_forecasts = {}
    for item in data['list']:
        date = datetime.fromtimestamp(item['dt']).strftime('%Y-%m-%d')
        if date not in daily_forecasts:
            daily_forecasts[date] = {
                'temp_min': item['main']['temp_min'],
                'temp_max': item['main']['temp_max'],
                'conditions': [],
                'icons': set()
            }
        else:
            daily_forecasts[date]['temp_min'] = min(daily_forecasts[date]['temp_min'], item['main']['temp_min'])
            daily_forecasts[date]['temp_max'] = max(daily_forecasts[date]['temp_max'], item['main']['temp_max'])
        
        daily_forecasts[date]['conditions'].append(item['weather'][0]['description'])
        daily_forecasts[date]['icons'].add(item['weather'][0]['icon'])
    
    # Process for response
    forecast_days = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    for date, values in daily_forecasts.items():
        if date == today:
            continue  # Skip today since we already have current weather
            
        forecast_days.append({
            'date': date,
            'day_name': datetime.strptime(date, '%Y-%m-%d').strftime('%A'),
            'temp_min': round(values['temp_min'], 1),
            'temp_max': round(values['temp_max'], 1),
            'main_condition': max(set(values['conditions']), key=values['conditions'].count),
            'icon': next(iter(values['icons']))  # Get first icon
        })
    
    return forecast_days[:5]  # Return next 5 days

def fetch_air_quality(lat, lon):
    params = {
        'lat': lat,
        'lon': lon,
        'appid': API_KEY
    }
    try:
        response = requests.get(AIR_POLLUTION_URL, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if not data or 'list' not in data or len(data['list']) == 0:
            return None
        
        aqi = data['list'][0]['main']['aqi']
        aqi_levels = {
            1: 'Good',
            2: 'Fair',
            3: 'Moderate',
            4: 'Poor',
            5: 'Very Poor'
        }
        
        return {
            'aqi': aqi,
            'level': aqi_levels.get(aqi, 'Unknown'),
            'components': data['list'][0]['components']
        }
    except requests.exceptions.RequestException as e:
        print(f"Air quality fetch error for lat {lat}, lon {lon}: {str(e)}")  # Debug log
        return None

if __name__ == '__main__':
    cache.clear()  # Clear cache on startup
    app.run(host='0.0.0.0', port=5000, debug=True) 
