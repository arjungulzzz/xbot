# track_followers.py
# Python script to track followers and trigger IFTTT

import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FollowerTracker:
    def __init__(self):
        self.target_username = os.getenv('TARGET_USERNAME', 'elonmusk')
        self.ifttt_key = os.getenv('IFTTT_WEBHOOK_KEY')
        self.ifttt_event = os.getenv('IFTTT_EVENT_NAME', 'twitter_follower_update')
        self.data_file = 'follower_data.json'
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def load_data(self):
        """Load historical follower data"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return {}
    
    def save_data(self, data):
        """Save follower data"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def get_follower_count(self, username):
        """Scrape follower count from multiple sources"""
        
        # Method 1: Try Nitter instances
        nitter_instances = [
            "https://nitter.net",
            "https://nitter.privacydev.net",
            "https://nitter.it"
        ]
        
        for instance in nitter_instances:
            try:
                url = f"{instance}/{username}"
                response = requests.get(url, headers=self.headers, timeout=15)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Look for follower count
                    stats = soup.find_all('span', class_='profile-stat-num')
                    for stat in stats:
                        parent = stat.find_parent()
                        if parent and 'follower' in parent.get_text().lower():
                            count_text = stat.get_text().strip()
                            # Handle K, M notation
                            if 'K' in count_text:
                                return int(float(count_text.replace('K', '')) * 1000)
                            elif 'M' in count_text:
                                return int(float(count_text.replace('M', '')) * 1000000)
                            else:
                                return int(count_text.replace(',', ''))
                
            except Exception as e:
                logger.warning(f"Nitter {instance} failed: {e}")
                continue
        
        # Method 2: Try Social Blade
        try:
            url = f"https://socialblade.com/twitter/user/{username}"
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for follower numbers
                numbers = soup.find_all(string=re.compile(r'^\d{1,3}(,\d{3})*$'))
                for num_text in numbers:
                    num = int(num_text.replace(',', ''))
                    if num > 1000:  # Reasonable follower count
                        return num
                        
        except Exception as e:
            logger.warning(f"Social Blade failed: {e}")
        
        return None
    
    def trigger_ifttt(self, event_data):
        """Trigger IFTTT webhook to post tweet"""
        if not self.ifttt_key:
            logger.error("IFTTT webhook key not set")
            return False
        
        try:
            url = f"https://maker.ifttt.com/trigger/{self.ifttt_event}/with/key/{self.ifttt_key}"
            
            response = requests.post(url, json=event_data, timeout=10)
            
            if response.status_code == 200:
                logger.info("IFTTT webhook triggered successfully")
                return True
            else:
                logger.error(f"IFTTT webhook failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error triggering IFTTT: {e}")
            return False
    
    def format_message(self, username, current_count, change, hours_ago, previous_count):
        """Format the tweet message"""
        current_formatted = f"{current_count:,}"
        
        if change is None:
            return f"📊 @{username} currently has {current_formatted} followers. (First tracking)"
        
        change_formatted = f"{abs(change):,}"
        
        if change > 0:
            emoji = "📈"
            change_text = f"+{change_formatted}"
            verb = "gained"
        elif change < 0:
            emoji = "📉" 
            change_text = f"-{change_formatted}"
            verb = "lost"
        else:
            emoji = "➡️"
            change_text = "0"
            verb = "no change"
        
        message = f"{emoji} @{username} {verb} {change_text} followers in ~{hours_ago:.0f}h\n\n"
        message += f"Current: {current_formatted}\n"
        if previous_count:
            message += f"Previous: {previous_count:,}\n"
        message += f"#TwitterStats"
        
        return message
    
    def calculate_change(self, current_count, history):
        """Calculate follower change from ~24 hours ago"""
        if not history:
            return None, None, None
        
        now = datetime.now()
        target_time = now - timedelta(hours=24)
        
        # Find closest record to 24 hours ago
        closest_record = None
        min_diff = float('inf')
        
        for record in history:
            record_time = datetime.fromisoformat(record['timestamp'])
            diff = abs((record_time - target_time).total_seconds())
            if diff < min_diff:
                min_diff = diff
                closest_record = record
        
        if closest_record:
            change = current_count - closest_record['followers_count']
            hours_ago = (now - datetime.fromisoformat(closest_record['timestamp'])).total_seconds() / 3600
            return change, hours_ago, closest_record['followers_count']
        
        return None, None, None
    
    def run(self):
        """Main execution function"""
        logger.info(f"Tracking followers for @{self.target_username}")
        
        # Get current follower count
        current_count = self.get_follower_count(self.target_username)
        if not current_count:
            logger.error("Could not get follower count")
            return False
        
        logger.info(f"Current followers: {current_count:,}")
        
        # Load historical data
        all_data = self.load_data()
        user_history = all_data.get(self.target_username, [])
        
        # Calculate change
        change, hours_ago, previous_count = self.calculate_change(current_count, user_history)
        
        # Add current record
        current_record = {
            'followers_count': current_count,
            'timestamp': datetime.now().isoformat()
        }
        user_history.append(current_record)
        
        # Keep only last 30 days
        cutoff = datetime.now() - timedelta(days=30)
        user_history = [
            r for r in user_history 
            if datetime.fromisoformat(r['timestamp']) > cutoff
        ]
        
        # Save data
        all_data[self.target_username] = user_history
        self.save_data(all_data)
        
        # Format message
        message = self.format_message(
            self.target_username, current_count, change, hours_ago, previous_count
        )
        
        print("Message to post:")
        print("=" * 50)
        print(message)
        print("=" * 50)
        
        # Trigger IFTTT to post tweet
        ifttt_data = {
            'value1': message,
            'value2': str(current_count),
            'value3': str(change) if change else '0'
        }
        
        success = self.trigger_ifttt(ifttt_data)
        
        if success:
            logger.info("Successfully triggered IFTTT webhook")
        else:
            logger.error("Failed to trigger IFTTT webhook")
        
        return success

if __name__ == "__main__":
    tracker = FollowerTracker()
    tracker.run()
