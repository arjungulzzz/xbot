# track_and_tweet.py
import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import logging
import tweepy
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TwitterFollowerBot:
    def __init__(self):
        self.target_username = os.getenv('TARGET_USERNAME', 'elonmusk')
        self.data_file = 'follower_data.json'
        
        # Twitter API credentials
        self.bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
        self.api_key = os.getenv('TWITTER_API_KEY')
        self.api_secret = os.getenv('TWITTER_API_SECRET')
        self.access_token = os.getenv('TWITTER_ACCESS_TOKEN')
        self.access_token_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
        
        # Initialize Twitter API
        self.setup_twitter_api()
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def setup_twitter_api(self):
        """Initialize Twitter API client"""
        try:
            self.client = tweepy.Client(
                bearer_token=self.bearer_token,
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
                wait_on_rate_limit=True
            )
            
            # Test authentication
            me = self.client.get_me()
            logger.info(f"Twitter API authenticated as: @{me.data.username}")
            
        except Exception as e:
            logger.error(f"Twitter API setup failed: {e}")
            self.client = None
    
    def get_follower_count(self, username):
        """Scrape follower count from multiple sources"""
        
        # Method 1: Try Nitter instances
        nitter_instances = [
            "https://nitter.net",
            "https://nitter.privacydev.net",
            "https://nitter.poast.org",
            "https://nitter.it"
        ]
        
        for instance in nitter_instances:
            try:
                url = f"{instance}/{username}"
                response = requests.get(url, headers=self.headers, timeout=15)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Look for follower count in various ways
                    # Method 1: profile-stat-num class
                    stats = soup.find_all('span', class_='profile-stat-num')
                    for i, stat in enumerate(stats):
                        # Followers usually at index 1
                        if i == 1:
                            count_text = stat.get_text().strip()
                            count = self.parse_count(count_text)
                            if count and count > 1000:  # Sanity check
                                logger.info(f"Got count from {instance}: {count:,}")
                                return count
                    
                    # Method 2: Look for text containing "followers"
                    follower_text = soup.find(string=re.compile(r'[\d,KM]+\s*[Ff]ollowers?'))
                    if follower_text:
                        match = re.search(r'([\d,KM]+)', follower_text)
                        if match:
                            count = self.parse_count(match.group(1))
                            if count and count > 1000:
                                logger.info(f"Got count from {instance} (text search): {count:,}")
                                return count
                
            except Exception as e:
                logger.warning(f"Nitter {instance} failed: {e}")
                continue
        
        # Method 2: Try Social Blade as backup
        try:
            url = f"https://socialblade.com/twitter/user/{username}"
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for numbers that could be follower counts
                all_text = soup.get_text()
                numbers = re.findall(r'\b(\d{1,3}(?:,\d{3})+)\b', all_text)
                
                for num_str in numbers:
                    num = int(num_str.replace(',', ''))
                    if 100000 <= num <= 500000000:  # Reasonable range
                        logger.info(f"Got count from Social Blade: {num:,}")
                        return num
                        
        except Exception as e:
            logger.warning(f"Social Blade failed: {e}")
        
        return None
    
    def parse_count(self, count_text):
        """Parse follower count text (handles K, M notation)"""
        if not count_text:
            return None
            
        count_text = count_text.strip().upper().replace(',', '')
        
        try:
            if 'K' in count_text:
                return int(float(count_text.replace('K', '')) * 1000)
            elif 'M' in count_text:
                return int(float(count_text.replace('M', '')) * 1000000)
            else:
                return int(count_text)
        except:
            return None
    
    def load_data(self):
        """Load historical data"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return {}
    
    def save_data(self, data):
        """Save data to file"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def calculate_change(self, current_count, history):
        """Calculate change from ~24 hours ago"""
        if not history:
            return None, None, None
        
        now = datetime.now()
        target_time = now - timedelta(hours=24)
        
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
    
    def format_tweet(self, username, current_count, change, hours_ago, previous_count):
        """Format tweet message (within 280 chars)"""
        current_formatted = f"{current_count:,}"
        
        if change is None:
            tweet = f"📊 @{username} currently has {current_formatted} followers.\n\n(First tracking)\n\n#FollowerTracker"
            return tweet
        
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
        
        # Keep it concise for Twitter's 280 char limit
        tweet = f"{emoji} @{username} {verb} {change_text} followers in ~{hours_ago:.0f}h\n\n"
        tweet += f"📊 {current_formatted}\n"
        tweet += f"📈 {change_text}\n\n"
        tweet += f"#FollowerTracker"
        
        # Truncate if too long
        if len(tweet) > 280:
            tweet = f"{emoji} @{username} {verb} {change_text} followers\n\n📊 {current_formatted} | 📈 {change_text}\n\n#FollowerTracker"
        
        return tweet
    
    def post_tweet(self, message):
        """Post tweet to Twitter"""
        if not self.client:
            logger.error("Twitter API client not available")
            return False
        
        try:
            response = self.client.create_tweet(text=message)
            tweet_id = response.data['id']
            tweet_url = f"https://twitter.com/i/status/{tweet_id}"
            logger.info(f"Tweet posted successfully: {tweet_url}")
            return True
            
        except Exception as e:
            logger.error(f"Error posting tweet: {e}")
            return False
    
    def run(self):
        """Main execution function"""
        logger.info(f"Tracking followers for @{self.target_username}")
        
        # Get current follower count
        current_count = self.get_follower_count(self.target_username)
        if not current_count:
            error_tweet = f"❌ Could not get follower count for @{self.target_username} today. Will try again tomorrow! #FollowerTracker"
            if self.client:
                self.post_tweet(error_tweet)
            logger.error("Could not get follower count")
            return False
        
        logger.info(f"Current followers: {current_count:,}")
        
        # Load and process data
        all_data = self.load_data()
        user_history = all_data.get(self.target_username, [])
        
        # Calculate change
        change, hours_ago, previous_count = self.calculate_change(current_count, user_history)
        
        # Add new record
        user_history.append({
            'followers_count': current_count,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep only last 30 days
        cutoff = datetime.now() - timedelta(days=30)
        user_history = [r for r in user_history if datetime.fromisoformat(r['timestamp']) > cutoff]
        
        # Save data
        all_data[self.target_username] = user_history
        self.save_data(all_data)
        
        # Format and post tweet
        tweet_text = self.format_tweet(self.target_username, current_count, change, hours_ago, previous_count)
        
        print("Tweet to post:")
        print("=" * 50)
        print(tweet_text)
        print(f"Characters: {len(tweet_text)}/280")
        print("=" * 50)
        
        # Post tweet
        success = self.post_tweet(tweet_text)
        
        if success:
            logger.info("Successfully posted follower update tweet!")
        else:
            logger.error("Failed to post tweet")
        
        return success

if __name__ == "__main__":
    bot = TwitterFollowerBot()
    bot.run()
