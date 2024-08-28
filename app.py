import os
import csv
import random
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

QUESTIONS_PER_PAGE = 20

def load_questions():
    questions = {}
    companies = []
    for filename in os.listdir('data'):
        if filename.endswith('.csv'):
            company = filename[:-4]
            companies.append(company)
            questions[company] = []
            with open(os.path.join('data', filename), 'r') as f:
                reader = csv.reader(f)
                for row in reader:
                    questions[company].append({
                        'id': row[1],
                        'name': row[2],
                        'url': f"https://leetcode.com/problems/{row[2].lower().replace(' ', '-')}",
                        'completed': False
                    })
    
    # Create a "General" category with all unique questions
    all_questions = set()
    for company_questions in questions.values():
        all_questions.update((q['id'], q['name']) for q in company_questions)
    
    questions['General'] = [
        {
            'id': q[0],
            'name': q[1],
            'url': f"https://leetcode.com/problems/{q[1].lower().replace(' ', '-')}",
            'completed': False
        } for q in all_questions
    ]
    
    return questions, ['General'] + sorted(companies)

questions, companies = load_questions()

@app.route('/')
def index():
    return render_template('index.html', companies=companies)

@app.route('/questions/<company>')
def get_questions(company):
    page = request.args.get('page', 1, type=int)
    company_questions = questions.get(company, [])
    total_pages = (len(company_questions) - 1) // QUESTIONS_PER_PAGE + 1
    start = (page - 1) * QUESTIONS_PER_PAGE
    end = start + QUESTIONS_PER_PAGE
    return jsonify({
        'questions': company_questions[start:end],
        'total_pages': total_pages,
        'current_page': page
    })

@app.route('/update_progress', methods=['POST'])
def update_progress():
    data = request.json
    company = data['company']
    question_id = data['questionId']
    completed = data['completed']
    
    for q in questions[company]:
        if q['id'] == question_id:
            q['completed'] = completed
            break
    
    # Update the "General" category as well
    if company != 'General':
        for q in questions['General']:
            if q['id'] == question_id:
                q['completed'] = completed
                break
    
    return jsonify({'success': True})

@app.route('/random_question/<company>')
def random_question(company):
    uncompleted = [q for q in questions[company] if not q['completed']]
    if uncompleted:
        return jsonify(random.choice(uncompleted))
    else:
        return jsonify({'message': 'All questions completed'})

@app.route('/reset_progress', methods=['POST'])
def reset_progress():
    for company in questions:
        for q in questions[company]:
            q['completed'] = False
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True)