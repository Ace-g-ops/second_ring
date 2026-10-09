import os
from dotenv import load_dotenv

load_dotenv()

##get the api key from the environment variable
BIMPEAI_API_KEY = os.getenv("BIMPEAI_API_KEY")
BIMPE_AGENT_ID=os.getenv("BIMPE_AGENT_ID")
TEST_PHONE_NUMBER=os.getenv("TEST_PHONE_NUMBER")

#get the data/logs dir
DATA_DIR= "data"
LOGS_DIR= "logs"

##get the paths for the data files
MISSED_CALLS_PATH=os.path.join(DATA_DIR,"missed_calls.json")
BOOKINGS_PATH=os.path.join(DATA_DIR,"bookings.json")
BUSINESS_INFO_PATH=os.path.join(DATA_DIR,"business_info.json")
CALL_RESULTS_PATH=os.path.join(DATA_DIR,"call_results.json")


