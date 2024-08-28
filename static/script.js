let completed_ids = [];

function loadQuestions(company) {
    fetch(`/questions/${company}`)
        .then(response => response.json())
        .then(data => {
            const questionList = document.getElementById('question-list');
            questionList.innerHTML = '';
            data.forEach(q => {
                const div = document.createElement('div');
                div.className = 'question-item';
                div.innerHTML = `
                    <a href="https://leetcode.com/problems/${q.name.replace(/\s+/g, '-').toLowerCase()}/" target="_blank">${q.name}</a>
                    <input type="checkbox" class="checkbox" data-id="${q.id}" onclick="toggleCompletion(${q.id})">
                `;
                questionList.appendChild(div);
            });
        });
}

function toggleCompletion(id) {
    if (completed_ids.includes(id)) {
        completed_ids = completed_ids.filter(item => item !== id);
    } else {
        completed_ids.push(id);
    }
}

function getRandomQuestion() {
    fetch('/recommend', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ completed_ids: completed_ids }),
    })
    .then(response => response.json())
    .then(data => {
        if (data.message === 'Good job!') {
            alert(data.message);
            // Optionally, clear all checkboxes
            document.querySelectorAll('.checkbox').forEach(checkbox => checkbox.checked = false);
            completed_ids = [];
        } else {
            alert(`Try this one next: ${data.name}`);
        }
    });
}
