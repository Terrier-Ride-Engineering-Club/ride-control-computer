from flask import Flask, render_template_string
import csv

app = Flask(__name__)

# Path to your data file
DATA_FILE = 'data.csv'


def load_data(file_path):
    data = []
    with open(file_path, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            data.append(row)
    return data


@app.route('/')
def index():
    return page_one()

@app.route('/one')
def page_one():
    return """
        <h1 style='text-align:center;'>data tba</h2>
        <div style="text-align:center; margin-top:20px;">
            <a href="/one"><button style="padding: 12px 24px; font-size:18px;"}>One</button></a>
            <a href="/two"><button style="padding: 12px 24px; font-size:18px;"}>Two</button></a>
        </div>"""


@app.route('/two')
def page_two():
    data = load_data(DATA_FILE)
    html = """
    <html>
    <head>
        <title>Data Viewer</title>
        <style>
            table { border-collapse: collapse; width: 60%; margin: 20px auto; }
            th, td { border: 1px solid #444; padding: 8px; text-align: center; }
            th { background-color: #eee; }
        </style>
    </head>
    <body>
        <h2 style=\"text-align:center;\">Time, Speed, and Position Data</h2>
        <table>
            <tr>
                <th>Time</th>
                <th>Speed</th>
                <th>Position</th>
            </tr>
            {% for row in data %}
            <tr>
                <td>{{ row.time }}</td>
                <td>{{ row.speed }}</td>
                <td>{{ row.position }}</td>
            </tr>
            {% endfor %}
        </table>
        <div style="text-align:center; margin-top:20px;">
            <a href="/one"><button style="padding: 12px 24px; font-size:18px;"}>One</button></a>
            <a href="/two"><button style="padding: 12px 24px; font-size:18px;"}>Two</button></a>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, data=data)



if __name__ == '__main__':
    app.run(debug=True)
