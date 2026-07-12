import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

def log_command(transcript, intent, response, source="voice"):
    supabase.table("commands_log").insert({
        "transcript": transcript,
        "intent": intent,
        "response": response,
        "source": source
    }).execute()

def get_automations():
    result = supabase.table("automations").select("*").execute()
    return result.data

def get_today_tasks():
    result = supabase.table("tasks").select("*").eq("done", False).execute()
    return result.data

def complete_task(task_id):
    result = supabase.table("tasks").update({"done": True}).eq("id", task_id).execute()
    return result.data