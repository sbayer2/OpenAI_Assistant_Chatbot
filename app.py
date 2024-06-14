from flask import Flask, request, jsonify, render_template_string
import openai
import time
import os

app = Flask(__name__)

openai.api_key = os.getenv('OPENAI_API_KEY')
client = openai.OpenAI(api_key=openai.api_key)
ASSISTANT = None
threads = {}
current_thread = None
assistant_name_global = "Assistant"

def submit_message(assistant_id, thread, user_message):
    run_status = get_active_run_status(thread.id)
    if run_status in ["queued", "in_progress"]:
        raise Exception("A run is still active, cannot add new message.")

    client.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=user_message
    )
    return client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant_id,
    )

def get_active_run_status(thread_id):
    try:
        runs = client.beta.threads.runs.list(thread_id=thread_id)
        if runs.data:
            return runs.data[-1].status
    except Exception as e:
        print(f"Error getting active run status: {e}")
    return None

def get_response(thread):
    return client.beta.threads.messages.list(thread_id=thread.id, order="asc")

def create_thread_and_run(user_input):
    thread = client.beta.threads.create()
    run = submit_message(ASSISTANT, thread, user_input)
    return thread, run

def wait_on_run(run, thread):
    while run.status in ["queued", "in_progress"]:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id,
        )
        time.sleep(0.5)
    return run

def create_thread_for_assistant(assistant_id):
    thread = client.beta.threads.create()
    threads[assistant_id] = thread
    return thread

@app.route('/create_assistant', methods=['POST'])
def create_assistant():
    global ASSISTANT
    global assistant_name_global
    global threads
    global current_thread

    assistant_name = request.form['assistant_name']
    instructions = request.form['instructions']
    personality = request.form['personality']
    model_type = request.form['model_type']
    assistant_name_global = assistant_name

    assistant_params = {
        "instructions": instructions,
        "name": assistant_name,
        "tools": [{"type": "code_interpreter"}],
        "model": model_type
    }

    try:
        response = client.beta.assistants.create(**assistant_params)
        ASSISTANT = response.id
        current_thread = create_thread_for_assistant(ASSISTANT)  # Create new thread for new assistant
        return jsonify({"message": "Assistant created", "assistant_id": ASSISTANT})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/delete_assistant', methods=['POST'])
def delete_assistant():
    global ASSISTANT
    global current_thread
    try:
        client.beta.assistants.delete(assistant_id=ASSISTANT)
        ASSISTANT = None
        current_thread = None  # Reset current thread
        return jsonify({"message": "Assistant deleted"})
    except Exception as e:
        return jsonify({"error": str(e)})

FORM_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>{{ assistant_name }}</title>
    <style>
        body { font-family: Arial, sans-serif; }
        form { margin-top: 20px; font-size: 18px; }
        label { display: block; margin-top: 10px; }
        input, select, textarea { font-size: 18px; padding: 10px; width: 100%; }
        #response { margin-top: 20px; padding: 10px; background-color: #f0f0f0; font-size: 18px; max-height: 800px; overflow-y: scroll; }
        #message { height: 40px; resize: none; }
        #send-button { font-size: 18px; padding: 10px 20px; }
    </style>
</head>
<body>
    <h1>{{ assistant_name }}</h1>
    <form id="create-assistant-form" method="POST">
        <label for="assistant-name">Assistant Name:</label>
        <input type="text" id="assistant-name" name="assistant_name" placeholder="Enter Assistant Name">
        <label for="instructions">Instructions:</label>
        <input type="text" id="instructions" name="instructions" placeholder="Enter Instructions">
        <label for="model-type">Model Type:</label>
        <input type="text" id="model-type" name="model_type" placeholder="Enter Model Type (e.g., gpt-4-turbo)">
        <label for="personality">Personality:</label>
        <select id="personality" name="personality">
            <option value="friendly">Friendly</option>
            <option value="professional">Professional</option>
            <option value="enthusiastic">Enthusiastic</option>
            <option value="helpful" selected>Helpful</option>
        </select>
        <button type="submit" id="send-button">Create Assistant</button>
    </form>
    <div id="customization-form" style="display:none;">
        <button id="delete-assistant">Delete Assistant</button>
        <form id="chat-form" method="POST">
            <input type="hidden" id="thread_id" name="thread_id">
            <label for="message">Enter Prompt:</label>
            <textarea id="message" name="user_input" placeholder="Type your message here"></textarea>
            <button type="submit" id="send-button">Send</button>
        </form>
    </div>
    <div id="response"></div>
<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
<script>
    $(function() {
        $('#create-assistant-form').on('submit', function(event) {
            event.preventDefault();
            var assistantName = $('#assistant-name').val();
            var instructions = $('#instructions').val();
            var modelType = $('#model-type').val();
            var personality = $('#personality').val();
            $.post('/create_assistant', {
                assistant_name: assistantName,
                instructions: instructions,
                model_type: modelType,
                personality: personality
            }, function(data) {
                if (data.assistant_id) {
                    $('#create-assistant-form').hide();
                    $('#customization-form').show();
                    $('title').text(assistantName);
                    $('h1').text(assistantName);
                    $('#response').html('');  // Clear the response box
                    alert('Assistant created with ID: ' + data.assistant_id);
                } else if (data.error) {
                    alert('Error creating assistant: ' + data.error);
                }
            });
        });

        $('#delete-assistant').on('click', function() {
            $.post('/delete_assistant', function(data) {
                if (data.message) {
                    $('#customization-form').hide();
                    $('#create-assistant-form').show();
                    $('title').text('Assistant');
                    $('h1').text('Assistant');
                    $('#response').html('');
                    // Clear the form fields
                    $('#create-assistant-form')[0].reset();
                    alert(data.message);
                } else if (data.error) {
                    alert('Error deleting assistant: ' + data.error);
                }
            });
        });

        $('#chat-form').on('submit', function(event) {
            event.preventDefault();
            var message = $('#message').val();
            var threadId = $('#thread_id').val();
            $.post('/', { user_input: message, thread_id: threadId }, function(data) {
                if (data.response) {
                    $('#response').html(data.response);
                    $('#message').val('');
                    $('#thread_id').val(data.thread_id);
                    $('#response').animate({ scrollTop: $('#response')[0].scrollHeight }, 'slow');
                } else if (data.error) {
                    $('#response').html('Error: ' + data.error);
                }
            });
        });
    });
</script>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def home():
    global threads
    global assistant_name_global
    global current_thread

    if request.method == 'POST':
        user_input = request.form['user_input']
        thread_id = request.form.get('thread_id')

        if not current_thread:
            return jsonify({'error': 'No current thread found. Please create an assistant first.'})

        try:
            run1 = submit_message(ASSISTANT, current_thread, user_input)
            run1 = wait_on_run(run1, current_thread)
        except Exception as e:
            return jsonify({'error': str(e)})

        messages = get_response(current_thread)
        formatted_response = "<br><br>".join(
            [f"{m.role.title()}: {m.content[0].text.value.replace('\n', '<br>')}" for m in messages.data])
        return jsonify({'response': formatted_response, 'thread_id': current_thread.id})

    return render_template_string(FORM_HTML, assistant_name=assistant_name_global)

@app.route('/readiness_check')
def readiness_check():
    if not os.environ.get("OPENAI_API_KEY"):
        return 'API key not set', 500
    return 'OK', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
