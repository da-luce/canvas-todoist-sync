import json
from datetime import datetime
from os import path
from re import sub
import traceback

from canvasapi import Canvas
import canvasapi.exceptions
import canvasapi.assignment
import canvasapi.quiz
import canvasapi.discussion_topic
from todoist_api_python.api import TodoistAPI
from prettytable import PrettyTable
from bs4 import BeautifulSoup
from dateutil import parser

import secrets

def truncate(string):
    return string[:10] + "..."

# Initialize a new Canvas object
try:
    canvas = Canvas(secrets.CANVAS_URL, secrets.CANVAS_KEY)
except:
    print("Failed to login to Canvas. Make sure you are using a valid API key")
    quit()

# Print Canvas login info
user = canvas.get_current_user()
print("Successfully logged into Canvas\n")
print("Name:\t" + user.name)
print("Email:\t" + user.get_profile()['primary_email'])
print("ID:\t" + str(user.id) +"\n")

# Initialize a new Todoist object
try:
    todo =  TodoistAPI(secrets.TODOIST_KEY)
except:
    print("Failed to login to Todpist. Make sure you are using a valid API key")
    quit()

# Print Todoist login info
print("\nSuccessfully logged into Todoist\n")

def print_ids():

    # Get list of active courses
    print("Fetching courses...")
    try:
        courses = canvas.get_courses(include=['term'], enrollment_state='active')
    except Exception:
        traceback.print_exc()
        return

    course_table = PrettyTable(['Course', 'ID'])
    for course in courses:
        course_table.add_row([course.name, str(course.id)])

    print(course_table)
    
    print("Fetching projects...")
    try:
        projects = todo.get_projects()
    except Exception:
        traceback.print_exc()
        return

    project_table = PrettyTable(['Project', 'ID'])
    for project in projects:
        project_table.add_row([project.name, project.id])

    print(project_table)

def sizePage(paginatedList):
    c = 0
    try:
        for i in paginatedList:
            c += 1
    except canvasapi.exceptions.ResourceDoesNotExist:
        c = 0
    return c

def parseTime(canvasTime):
   
    if canvasTime is None:
        return None

    # get datetime object from canavs timestamp in ISO 8601 format (UTC time zone)
    dt = parser.parse(canvasTime)
    
    # Put time in format that Todoist can better understand
    return dt.strftime("due %m/%d/%Y at %I %p")

def sync():

    # Set up link file
    if (not path.exists("sync.json")):
        print("You dont't seem to have a link file. Create link.json in the current directory")
        quit()

    with open('sync.json', 'r') as f:
        data = json.load(f)
        f.close()

    if (len(data) == 0):
        print("You don't appear to have any linked courses")
        quit()

    print("Link file found. Beggining sync...\n")

    for link in data:

        courseID = link['courseID']
        projectID = link['projectID']

        # Fetch course
        print("Fetching course with ID '" + courseID + "'...", end='\t\t')
        try:
            course = canvas.get_course(courseID)
        except Exception:
            print("❌ Error getting course")
            traceback.print_exc()
            continue
        print("✅ Successfully found course '" + course.name + "'")

        # Fetch project
        print("Fetching project with ID '" + projectID + "'...", end='\t')
        try:
            project = todo.get_project(project_id=projectID)
        except Exception:
            print("❌ Error getting project")
            traceback.print_exc()
            continue
        print("✅ Successfully found project '" + project.name + "'")

        print("\nSyncing '" + course.name + "' with '" + project.name + "'...")

        for item in link['items']:

            sectionID = None
            labels    = []

            if 'sectionID' in item:
                sectionID = item['sectionID']

            if 'labels' in item:
                labels = item['labels']

            # Fetch items from Canvas
            match item['type']:
                case "assignment":
                    items = course.get_assignments(bucket = 'unsubmitted')
                case "quiz":
                    items = course.get_quizzes()
                case "discussion":
                    items = course.get_discussion_topics(scope = "unlocked")
                case _:
                    print("\t❌ Could not recognize type '" + item['type'] + "'. Type must be Assignment, Quiz, or Discussion")
                    continue

            itemType = item['type'] 
            if (sizePage(items) == 0):
                print("\t✔️ " + itemType.capitalize() + ":\tNo items of type " + itemType + " to sync in " + course.name)
                continue

            print("\t🔁 " + itemType.capitalize() + ":\tSyncing " + str(sizePage(items)) + " " + itemType + " in '" + course.name + "' to '" + project.name + "'")

            # Create tasks
            numDups = 0
            for i in items:

                if type(i) == "quiz":
                    if (i.locked_for_user):
                        continue

                if dup_task(i.id, projectID, sectionID):
                    numDups += 1
                    continue

                parent_id = create_task(
                    i,
                    item.get('project_id'),
                    item.get('section_id'),
                    item.get('labels'),
                    item.get('priority')
                )

                # Create subtasks if applicable
                if ('subtasks' in item):
                    for subtask in item['subtasks']:

                        create_subtask(
                            subtask.get('content'),
                            subtask.get('description'), 
                            parent_id,
                            subtask.get('labels'),
                            subtask.get('priority'),
                            subtask.get('due_string')
                        )

# Create a subtask
def create_subtask(content, description, parent_id, labels, priority, due_string):

    # Get due date of parent 
    try:
        parent = todo.get_task(task_id=parent_id)
    except Exception:
        traceback.print_exc()
        return

    # If no parent due date, don't set any due date
    if parent.due is None:
        parentDue = ""
        due_string = ""
    else:
        parentDue = parent.due.string

    content     = content       or "No name"
    description = description   or ""
    labels      = labels        or []
    priority    = priority      or 1
    due_string  = due_string    or ""

    try:
        todo.add_task(
            content     = content,
            description = description,
            parent_id   = parent_id,
            labels      = labels,
            priority    = priority,
            due_string  = due_string + parentDue,
        )
    except Exception:
        traceback.print_exc()
        return

    print("\t\t\t\t✅ Created subtask '" + content + "'")


# Create a task give an assignment, quiz, or dicussion
def create_task(item, project_id, section_id, labels, priority):

    content     = ""
    description = ""
    project_id  = project_id or None
    section_id  = section_id or None
    labels      = labels or []
    priority    = priority or 1
    due_string  = ""

    # Switch case due to inconsistent naming in Canvas API
    match type(item):

        case canvasapi.assignment.Assignment:
            content     = item.name
            description = item.description
            due_string  = item.due_at
        case canvasapi.quiz.Quiz:
            content     = item.title
            description = item.description
            due_string  = item.due_at
        case canvasapi.discussion_topic.DiscussionTopic:
            content     = item.title
            description = BeautifulSoup(item.message, "html.parser").get_text()
            due_string  = item.lock_at
        case _:
            print("\t\t\t❌ Error! " + str(type(item)) + " did not match any types available")
            return

    time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    try:
        task = todo.add_task(
            content     = content,
            description = description + "\nAutocreated at " + time + "\nCanvas ID: " + str(item.id),
            project_id  = project_id,
            section_id  = section_id,
            priority    = priority,
            labels      = labels,
            due_string  = parseTime(due_string),
            due_lang    = "en",
        )
    except Exception as error:
        print("\t\t\t❌ Failed to create task '" + content + "'")
        print(error)
        return

    print("\t\t\t✅ Created task '" + content + "'")

    return task.id, task.due;

# Check for dupilcate get_tasks_sync
# itemID: ID number of the assignment, quiz, etc...
# projectID: ID number of Todoist project
# sectionID: ID number of Todoist section
# TODO: does supplying both projectID and sectionID break things?
def dup_task(itemID, projectID=None, sectionID=None):

    try:
        tasks = todo.get_tasks(project_id=projectID, section_id=sectionID)
    except Exception as error:
        print("Error checking for duplicate tasks!")
        print(error)

        # In case of error, treat as if duplicate task (don't create a new one)
        return True

    for task in tasks:
        if str(itemID) in task.description:
            print("\t\t\tℹ️ Duplicate task found for " + task.content)
            return True

    return False

sync()
