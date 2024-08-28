import os
import csv
import random
from collections import defaultdict
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

QUESTIONS_PER_PAGE = 20

user_stats = {
    'solved_tags': defaultdict(int),
    'solved_difficulties': defaultdict(int),
    'solved_questions': set()
}

def load_questions():
    questions = {}
    companies = []
    for filename in os.listdir('data'):
        if filename.endswith('.csv'):
            company = filename[:-4]
            companies.append(company)
            questions[company] = []
            with open(os.path.join('data', filename), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    questions[company].append({
                        'id': row[1],
                        'name': row[2],
                        'difficulty': row[3],
                        'tags': row[4].split(','),
                        'url': f"https://leetcode.com/problems/{row[2].lower().replace(' ', '-')}",
                        'completed': False
                    })
    
    all_questions = set()
    for company_questions in questions.values():
        all_questions.update((q['id'], q['name'], q['difficulty'], ','.join(q['tags'])) for q in company_questions)
    
    questions['All'] = [
        {
            'id': q[0],
            'name': q[1],
            'difficulty': q[2],
            'tags': q[3].split(','),
            'url': f"https://leetcode.com/problems/{q[1].lower().replace(' ', '-')}",
            'completed': False
        } for q in all_questions
    ]
    
    return questions, ['All'] + sorted(companies)

questions, companies = load_questions()

@app.route('/')
def index():
    return render_template('index.html', companies=companies)

@app.route('/questions/<company>')
def get_questions(company):
    page = request.args.get('page', 1, type=int)
    tag_filter = request.args.get('tag', None)
    company_questions = questions.get(company, [])
    
    if tag_filter:
        company_questions = [q for q in company_questions if tag_filter in q['tags']]
    
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
    
    if company != 'All':
        for q in questions['All']:
            if q['id'] == question_id:
                q['completed'] = completed
                break
    
    # Update user stats
    if completed:
        user_stats['solved_questions'].add(question_id)
        for tag in q['tags']:
            user_stats['solved_tags'][tag] += 1
        user_stats['solved_difficulties'][q['difficulty']] += 1
    else:
        user_stats['solved_questions'].discard(question_id)
        for tag in q['tags']:
            user_stats['solved_tags'][tag] = max(0, user_stats['solved_tags'][tag] - 1)
        user_stats['solved_difficulties'][q['difficulty']] = max(0, user_stats['solved_difficulties'][q['difficulty']] - 1)
    
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
    
    # Reset user stats
    user_stats['solved_tags'].clear()
    user_stats['solved_difficulties'].clear()
    user_stats['solved_questions'].clear()
    
    return jsonify({'success': True})

@app.route('/recommend_question', methods=['GET'])
def recommend_question():
    company = request.args.get('company', 'All')
    possible_questions = [q for q in questions[company] if not q['completed']]
    
    # Prioritize questions based on user stats
    possible_questions.sort(key=lambda q: (
        user_stats['solved_tags'][q['tags'][0]] if q['tags'] else 0,
        user_stats['solved_difficulties'][q['difficulty']]
    ))
    
    if possible_questions:
        return jsonify(possible_questions[0])
    else:
        return jsonify({'message': 'All questions completed'})

if __name__ == '__main__':
    app.run(debug=True)
