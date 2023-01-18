# About

A simple script for adding assignments, quizzes, and discussions from [Canvas](https://www.instructure.com/canvas?domain=canvas/) to [Todoist](https://todoist.com/). Designed to be felxible and powerful. Contributions are welcome.

# Getting started

### Authentication

Create a file `secrets.json` in the same directory as the script. Input your API keys and Canvas URL (your school's Canvas domain, e.g. (https://canvas.cornell.edu/)[https://canvas.cornell.edu/]) as shown:

```py
CANVAS_URL = "..."
CANVAS_KEY = "..."
TODOIST_KEY = "..."
```
### Settings

Create a file `sync.json` in the same directory as the script. This file contains an arbitrary number of "link" objects (one shown below), which defines what data will be pushed from a Canvas course to a corresponding Todoist project. Example:

```json
[
    {
        "course_id":"12345",
        "project_id":"1234567890",
        "posts":
        [
            {
                "type":"assignment",
                "section_id":"1234567890",
                "labels":["Auto", "Assignment"]
                "subtasks":
                [
                    {
                        "content":"Complete!",
                        "description":"Example subtask",
                        "labels":["Auto"],
                        "due_string":"one day before"
                    }
                ]
            },
            {
                "type":"quiz",
                "section_id":"1234567890",
                "labels":["Auto", "Quiz"]
            },
            {
                "type":"discussion",
                "section_id":"1234567890",
                "labels":["Auto", "Discussion"]
            }
        ]
    }
]
```
### Key explanations

Primary keys:

- **course_id:**  the ID of the canvas course (required)
- **project_id:** the ID of the Todoist project (required)
- **posts:**      list of rules for pushing data (required)

Post keys:
- **type:**       the type of post to push from Canvas, can be assignment, quiz, or discussion (required)
- **section_id:** section to push tasks to
- **labels:**     labels to add to autocreated tasks
- **subtasks:**   list of subtasks to add to primary task

Subtask keys:
- **content:**      name of the subtask (required)
- **description:**  description of the subtask
- **labels:**       labels to add to the subtask
- **due_string:**   concatenated with parent task due date. Thus a due string of "one day before" will make the subtask due one day before the parent task

# Notes, Recommendations, and Warnings
- Add a label such as `Auto` to all automatically created tasks. This makes it easy to filter and delete autocreated tasks
- Helper functions `printCanvasID` and `printTodoistID` are included for easy determination of course and/or project IDs
- ⚠️ Warning: this project is a work in progress, there may be some bugs

