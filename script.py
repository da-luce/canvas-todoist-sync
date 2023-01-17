import json
from datetime import datetime
from os import path

from canvasapi import Canvas
import canvasapi.exceptions
import canvasapi.assignment
import canvasapi.quiz
import canvasapi.discussion_topic
from todoist_api_python.api import TodoistAPI
from prettytable import PrettyTable

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
    courses = canvas.get_courses(include=['term'], enrollment_state='active')

    course_table = PrettyTable(['Course', 'ID'])
    for course in courses:
        course_table.add_row([course.name, str(course.id)])

    print(course_table)

    projects = todo.get_projects()

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

    for link in data:
 
        courseID = link['courseID']
        projectID = link['projectID']

        try:
            course = canvas.get_course(courseID)
        except Exception as error:
            print("Error getting course with ID '" + courseID + "'")
            print(error)
            continue

        try:
            project = todo.get_project(project_id=projectID)
        except:
            print("Error getting project with ID'" + projectID + "'")
            continue

        print("Attempting to sync Canvas course '" + course.name + "' with Todoist project '" + project.name + "'")

        for item in link['items']:

            sectionID = None
            labels    = []

            if 'sectionID' in item:
                sectionID = item['sectionID']

            if 'labels' in item:
                labels = item['labels']

            # Fetch items from Canvas
            match item['type']:
                case "Assignment":
                    items = course.get_assignments(bucket = 'unsubmitted')
                case "Quiz":
                    items = course.get_quizzes()
                case "Discussion":
                    items = course.get_discussion_topics(scope = "unlocked")
                case _:
                    print("\t○ Error: Could not recognize type '" + item['type'] + "'. Type must be Assignment, Quiz, or Discussion")
                    continue

            itemType = item['type'] 
            if (sizePage(items) == 0):
                print("\t○ No " + itemType + "s to sync in " + course.name)
                continue
            print("\t○ Syncing " + str(sizePage(items)) + " " + itemType + " in " + course.name + " to " + project.name)

            # Create tasks
            for i in items:

                if type(i) == "quiz":
                    if (i.locked_for_user):
                        continue

                if dup_task(i.id, projectID, sectionID):
                    continue

                create_task(i, labels, projectID, sectionID)

# Create a task give an assignment, quiz, or dicussion
def create_task(item, labels=[], projectID=None, sectionID=None):

    content     = ""
    due_date    = ""
    description = ""

    # Switch case due to inconsistent naming in Canvas API
    match type(item):

        case canvasapi.assignment.Assignment:
            content     = item.name
            due_date    = item.due_at
            description = item.description
        case canvasapi.quiz.Quiz:
            content     = item.title
            due_date    = item.due_at
            description = item.description
        case canvasapi.discussion_topic.DiscussionTopic:
            content     = item.title
            due_date    = item.lock_at
            description = item.message
        case _:
            print("\t\tError! " + str(type(item)) + " did not match any types available")

    time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    try:
        todo.add_task(
            content     = content,
            due_string  = due_date,
            due_lang    = "en",
            project_id  = projectID,
            section_id  = sectionID,
            description = description + "\n\n\n Autocreated at " + time + "\nCanvas ID: " + str(item.id),
            labels      = labels
        )
    except Exception as error:
        print("\t\tError creating task for " + str(type(item)) + " '" + content + "'")
        print(error)
        return

    print("\t\tSuccessfully created task for '" + content + "'!")

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
            print("\t\tDuplicate task found for " + task.content)
            return True

    return False

print_ids()
sync()
