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


def push_all():

    """

    Attempts to push all items defined in sync.json from Canvas to Todoist, for all defined courses.
    Recognizes duplicates by checking for the Canvas item's ID in the task description.

    """

    data = get_link_data()

    # Iterate through all links between courses and projects
    for link in data:

        # Ensure link contains courseID and projectID
        try:
            course_id = link['course_id']
            project_id = link['project_id']
        except:
            print("❌ Error: courseID and/or projectID not found in link")
            continue

        course = get_course(course_id)
        if course is None: continue

        project = get_project(project_id)
        if project is None: continue

        print(f"\nPushing '{course.name}' to '{project.name}'...")

        if 'posts' not in link:
            print("Link contains no defined posts to push")
            continue

        # Iterate through all defined post actions in link
        for postDefinition in link['posts']:

            # Fetch posts from Canvas
            posts = get_posts(course, postDefinition['type'])
            if posts is None: continue

            # Create tasks
            for post in posts:

                # Ignore if existing task
                if existing_task(post.id, project_id, postDefinition.get('section_id')):
                    continue

                # Create task
                parent_id = create_primary_task(
                    post,
                    project_id,
                    postDefinition.get('section_id'),
                    postDefinition.get('labels'),
                    postDefinition.get('priority')
                )

                # Create subtasks if applicable
                if ('subtasks' in postDefinition):

                    for subtask in postDefinition['subtasks']:

                        create_subtask(
                            subtask.get('content'),
                            subtask.get('description'), 
                            parent_id,
                            subtask.get('labels'),
                            subtask.get('priority'),
                            subtask.get('due_string')
                        )


def get_link_data():

    """

    Retrieves data from sync.json file.

    :return: a Python dictionary containing the contents of sync.json

    """
    if (not path.exists("sync.json")):
        print("You dont't seem to have a link file. Create link.json in the current directory")
        quit()

    try:
        with open('sync.json', 'r') as f:
            data = json.load(f)
            f.close()
    except:
        print("Error opening sync.json")
        quit()

    if (len(data) == 0):
        print("You don't appear to have any linked courses")
        quit()

    print("Link file found. Beggining push...\n")
    return data


def get_course(course_id):

    """

    Fetchs a Canvas course given its ID

    :param course_id: the five digit identifier of the course

    :return: A canvasapi.course.Course object representing the desired course

    """

    print(f"Fetching course with ID '{course_id}'...", end='\t\t')

    try:
        course = canvas.get_course(course_id)
    except Exception:
        print(f"❌ Error getting course with ID '{course_id}'")
        traceback.print_exc()
        return

    print(f"✅ Successfully found course '{course.name}'")

    return course


# Fetch a Todoist project
def get_project(project_id):

    print(f"Fetching project with ID '{project_id}'...", end='\t')

    try:
        project = todo.get_project(project_id=project_id)
    except Exception:
        print(f"❌ Error getting project with ID '{project_id}'")
        traceback.print_exc()
        return

    print(f"✅ Successfully found project '{project.name}'")

    return project


def get_posts(course, type):

    """

    Returns 'posts' from a Canvas course

    :param course: A canvasapi.course.Course object representing the desired course_id
                   (used instead of course_id to help limit API calls)
    :param type: A string representing the type of course. Can be 'assignment', 'quiz', or 'discussion'

    """

    # Use corresponding API for post type
    match type:

        case "assignment":
            # Ignore unsubmitted assignments
            posts = course.get_assignments(bucket = 'unsubmitted')

        case "quiz":
            # Ignore locked quizzes
            posts = []
            quizzes = course.get_quizzes()

            if size_page(quizzes) != 0:
                for quiz in quizzes:
                    if not quiz.locked_for_user:
                        posts.append(quiz)

        case "discussion":
            # Ignore locked discussions
            posts = course.get_discussion_topics(scope = "unlocked")

        case _:
            print(f"\t❌ Could not recognize type '{type}'. Type must be Assignment, Quiz, or Discussion")
            return

    # If no posts, return empty
    if (size_page(posts) == 0):
        print(f"\t✔️ {type.capitalize()} :\tNo items of type {type} to sync")
        return

    print(f"\t🔁 {type.capitalize()} :\tPushing {str(size_page(posts))} post(s) of type {type} from '{course.name}'")

    return posts


def create_primary_task(post, project_id, section_id, labels, priority):

    """

    Create a task given an assignment, quiz or discussions

    :param post: canvasapi.assignment.Assignment, canvasapi.quiz.Quiz, or canvasapi.discussion_topic.DiscussionTopic object
    :param project_id: the integer identifier of the project the task will be created in (optional)
    :param section_id: the integer identifier of the section the task will be created in (optional)
    :param labels: a list of strings containing labels to be applied to the task (optional)
    :param priority: an integer value describing the priority of the task (normal - 1, through high - 4) (optional)
                     note: the API uses priority 1 as normal, while the desltop/mobile/web clients use 4 as normal (reversed)

    """

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
            print(f"\t\t\t❌ Error! {str(type(post))} did not match any types available")
            return

    time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    try:
        task = todo.add_task(
            content     = content,
            description = description + f"\n`Autocreated {time} `\n`Canvas ID: {str(post.id)}`",
            project_id  = project_id,
            section_id  = section_id,
            priority    = priority,
            labels      = labels,
            due_string  = parse_time(due_string),
            due_lang    = "en",
        )
    except Exception as error:
        print(f"\t\t\t❌ Failed to create task '{content}'")
        print(error)
        return

    if section_id:
        section_name = todo.get_section(section_id=section_id).name
        print(f"\t\t\t✅ Created task '{content}' in section '{section_name}'")
    else:
        print(f"\t\t\t✅ Created task '{content}'")

    return task.id


def create_subtask(content, description, parent_id, labels, priority, due_string):

    """

    Creates a subtask under an autogenerated task

    :param content: the 'name' of the subtask
    :param description: the description of the subtask
    :param parent_id: the integer identifier of the parent task (required)
    :param labels: a list of strings containing labels to be applied to the subtask
    :param priority: an integer describing the priority of the subtask (see create_primary_task())
    :param due_string: a string describing when the subtask should be due in relation to the parent task
                       e.g. a value of 'one day before' makes the subtask due one day before the parent task

    """

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

    print(f"\t\t\t\t✅ Created subtask '{content}'")


def existing_task(post_id, project_id, section_id):

    """

    Check for duplicate tasks

    :param post_id: the integer identifier of the Canvas post (assignment, quiz, or discussion)
    :param project_id: the integer identifier of the project to search for tasks in
    :param section_id: the integer identifier of the section to search for tasks in

    :return: True if a task already exists with the same post_id in its description. Otherwise False

    """

    try:
        tasks = todo.get_tasks(project_id=project_id, section_id=section_id)
    except Exception as error:
        print("Error checking for existing task!")
        print(error)

        # In case of error, treat as if duplicate task (don't create a new one)
        return True

    for task in tasks:
        if str(post_id) in task.description:
            print(f"\t\t\tℹ️ Existing task found for '{task.content}'")
            return True

    return False


def delete_task(task_id):

    """

    Deletes a gven task

    :param task_id: the integer identifier of the task to delete

    """

    try:
        todo.delete_task(task_id=task_id)
    except:
        traceback.print_exc()
        print("Error deleting task")
        return

    print(f"Successfully deleted task with ID '{task_id}'")


def print_canvas_id():

    """

    Prints the integer identifiers of user's Canvas courses 

    """

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


def print_todoist_id():

    """

    Prints integer indentifiers of the user's Todoist projects and their respective sections

    """

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


def size_page(paginatedList):

    """

    Returns the size of a PaginatedList

    :param paginatedList: a canvasapi.paginated_list.PaginatedList object

    :return: the number of items in the list

    """

    count = 0

    try:
        for i in paginatedList:
            count += 1

    # Exception thrown when list is empty
    except canvasapi.exceptions.ResourceDoesNotExist:
        count = 0

    return count


def parse_time(canvasTime):

    """

    Parses Canvas timestamps to a string readable by Todoist's AI

    """

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

    #print_canvas_id()
    #print_todoist_id()
    push_all()
