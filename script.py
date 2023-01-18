import json
import traceback
from os import path
from dateutil import parser
from datetime import datetime
from bs4 import BeautifulSoup
from prettytable import PrettyTable

from canvasapi import Canvas
import canvasapi.exceptions
import canvasapi.assignment
import canvasapi.quiz
import canvasapi.discussion_topic

from todoist_api_python.api import TodoistAPI

import secrets


# Push items defined in sync.json from Canvas to Todoist (recognizes duplicates) for all courses
def pushAll():

    data = getLinkData()

    # Iterate through all links between courses and projects
    for link in data:

        # Ensure link contains courseID and projectID
        try:
            course_id = link['course_id']
            project_id = link['project_id']
        except:
            print("❌ Error: courseID and/or projectID not found in link")
            continue

        course = getCourse(course_id)
        if course is None: continue

        project = getProject(project_id)
        if project is None: continue

        print("\nPushing '" + course.name + "' to '" + project.name + "'...")

        if 'posts' not in link:
            print("Link contains no defined posts to push")
            continue

        # Iterate through all defined post actions in link
        for postDefinition in link['posts']:

            # Fetch posts from Canvas
            posts = getPosts(course, postDefinition['type'])
            if posts is None: continue

            # Create tasks
            for post in posts:

                # Ignore if existing task
                if existingTask(post.id, project_id, postDefinition.get('section_id')):
                    continue

                # Create task
                parent_id = createPrimaryTask(
                    post,
                    project_id,
                    postDefinition.get('section_id'),
                    postDefinition.get('labels'),
                    postDefinition.get('priority')
                )

                # Create subtasks if applicable
                if ('subtasks' in postDefinition):

                    for subtask in postDefinition['subtasks']:

                        createSubtask(
                            subtask.get('content'),
                            subtask.get('description'), 
                            parent_id,
                            subtask.get('labels'),
                            subtask.get('priority'),
                            subtask.get('due_string')
                        )


# Retrieve data from sync.json
def getLinkData():

    if (not path.exists("sync.json")):
        print("You dont't seem to have a link file. Create link.json in the current directory")
        quit()

    with open('sync.json', 'r') as f:
        data = json.load(f)
        f.close()

    if (len(data) == 0):
        print("You don't appear to have any linked courses")
        quit()

    print("Link file found. Beggining push...\n")
    return data


# Fetch a Canvas course
def getCourse(course_id):

    print("Fetching course with ID '" + course_id + "'...", end='\t\t')

    try:
        course = canvas.get_course(course_id)
    except Exception:
        print("❌ Error getting course with ID '" + course_id + "'")
        traceback.print_exc()
        return

    print("✅ Successfully found course '" + course.name + "'")

    return course


# Fetch a Todoist project
def getProject(project_id):

    print("Fetching project with ID '" + project_id + "'...", end='\t')

    try:
        project = todo.get_project(project_id=project_id)
    except Exception:
        print("❌ Error getting project with ID '" + project_id + "'")
        traceback.print_exc()
        return

    print("✅ Successfully found project '" + project.name + "'")

    return project


# Get posts from Canvas course given a canvasapi.course.Course object and a type of post
def getPosts(course, type):

    # Use corresponding API for post type
    match type:

        case "assignment":
            # Ignore unsubmitted assignments
            posts = course.get_assignments(bucket = 'unsubmitted')

        case "quiz":
            # Ignore locked quizzes
            posts = []
            quizzes = course.get_quizzes()

            if sizePage(quizzes) != 0:
                for quiz in quizzes:
                    if not quiz.locked_for_user:
                        posts.append(quiz)

        case "discussion":
            # Ignore locked discussions
            posts = course.get_discussion_topics(scope = "unlocked")

        case _:
            print("\t❌ Could not recognize type '" + type + "'. Type must be Assignment, Quiz, or Discussion")
            return

    # If no posts, return empty
    if (sizePage(posts) == 0):
        print("\t✔️ " + type.capitalize() + ":\tNo items of type " + type + " to sync")
        return

    print("\t🔁 " + type.capitalize() + ":\tPushing " + str(sizePage(posts)) + " posts of type " + type + " from " + course.name)

    return posts


# Autocreate a task give an assignment, quiz, or dicussion
def createPrimaryTask(post, project_id, section_id, labels, priority):

    content     = ""
    description = ""
    project_id  = project_id or None
    section_id  = section_id or None
    labels      = labels or []
    priority    = priority or 1
    due_string  = ""

    # Switch case due to inconsistent naming in Canvas API
    match type(post):

        case canvasapi.assignment.Assignment:
            content     = post.name
            description = post.description
            due_string  = post.due_at
        case canvasapi.quiz.Quiz:
            content     = post.title
            description = post.description
            due_string  = post.due_at
        case canvasapi.discussion_topic.DiscussionTopic:
            content     = post.title
            description = BeautifulSoup(post.message, "html.parser").get_text()
            due_string  = post.lock_at
        case _:
            print("\t\t\t❌ Error! " + str(type(post)) + " did not match any types available")
            return

    time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    try:
        task = todo.add_task(
            content     = content,
            description = description + "\n`Autocreated " + time + "`\n`Canvas ID: " + str(post.id) + "`",
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

    if section_id:
        section_name = todo.get_section(section_id=section_id).name
        print("\t\t\t✅ Created task '" + content + "' in section " + section_name)
    else:
        print("\t\t\t✅ Created task '" + content + "'")

    return task.id


# Create a subtask under an autogenerated task
def createSubtask(content, description, parent_id, labels, priority, due_string):

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


# Check for dupilcate get_tasks_sync
# itemID: ID number of the assignment, quiz, etc...
# projectID: ID number of Todoist project
# sectionID: ID number of Todoist section
# TODO: does supplying both projectID and sectionID break things?
def existingTask(post_id, project_id, section_id):

    try:
        tasks = todo.get_tasks(project_id=project_id, section_id=section_id)
    except Exception as error:
        print("Error checking for existing task!")
        print(error)

        # In case of error, treat as if duplicate task (don't create a new one)
        return True

    for task in tasks:
        if str(post_id) in task.description:
            print("\t\t\tℹ️ Existing task found for '" + task.content + "'")
            return True

    return False


# Print IDs for Canvas courses
def printCanvasID():

    print("Fetching courses...")

    # Only request active courses
    try:
        courses = canvas.get_courses(
            include = ['term'],
            enrollment_state = 'active'
        )
    except Exception:
        traceback.print_exc()
        return

    # Create and print course table
    course_table = PrettyTable(['Course', 'ID'])

    for course in courses:
        course_table.add_row([course.name, str(course.id)])

    print(course_table)


# Print IDs for Todoist projects and sections
def printTodoistID():

    print("Fetching projects and sections...\n")

    # Request all projects
    try:
        projects = todo.get_projects()
    except Exception:
        traceback.print_exc()
        return

    # Iterate through projects and print corresponding sections
    for project in projects:

        sections = todo.get_sections(project_id=project.id)

        print(project.name + ": " + project.id)

        for section in sections:
            print("\t" + section.name + ": " + section.id)


# Returns size of a PaginatedList (internal class of canvasapi)
def sizePage(paginatedList):

    count = 0

    try:
        for i in paginatedList:
            count += 1

    # Exception thrown when list is empty
    except canvasapi.exceptions.ResourceDoesNotExist:
        count = 0

    return count


# Parse Canvas timestamps to string readable by Todoist's AI
def parseTime(canvasTime):

    if canvasTime is None:
        return None

    # Datetime object from canavs timestamp in ISO 8601 format (UTC time zone)
    dt = parser.parse(canvasTime)

    # Put time in format that Todoist can better understand
    return dt.strftime("due %m/%d/%Y at %I %p")


if __name__ == "__main__":

    # Initialize a new Canvas object
    try:
        canvas = Canvas(secrets.CANVAS_URL, secrets.CANVAS_KEY)
    except:
        print("Failed to login to Canvas. Make sure you are using a valid API key")
        quit()

    print("Successfully logged into Canvas")

    # Initialize a new Todoist object
    try:
        todo =  TodoistAPI(secrets.TODOIST_KEY)
    except:
        print("Failed to login to Todoist. Make sure you are using a valid API key")
        quit()

    print("Successfully logged into Todoist\n")

    #printCanvasID()
    #printTodoistID()
    pushAll()
