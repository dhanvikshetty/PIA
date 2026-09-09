import { useState } from 'react';
import { Users } from 'lucide-react';
import { HR_QUESTIONS } from '../data/hrQuestions';

// HR view sizes — Top 10 / 50 / 100
const HR_VIEWS = [
  { id: 10, label: 'Top 10' },
  { id: 50, label: 'Top 50' },
  { id: 100, label: 'Top 100' },
];

export default function HrQuestionsPage() {
  const [hrView, setHrView] = useState(10);

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">HR Qss</h1>
        <p className="page-subtitle">
          The most common HR &amp; behavioural questions asked in software interviews —
          ordered by how often they come up. Switch between the top 10, 50 or all 100.
        </p>
      </div>

      <div className="page-body">
        <div className="fp-col hr-page-col">
          <div className="fp-col-title">
            <Users size={15} /> HR Questions
            <span className="fp-section-count">{hrView} of {HR_QUESTIONS.length}</span>
          </div>

          <div className="fp-hr-views">
            {HR_VIEWS.map((v) => (
              <button
                type="button"
                key={v.id}
                className={`fp-hr-view ${hrView === v.id ? 'fp-hr-view-active' : ''}`}
                onClick={() => setHrView(v.id)}
              >
                {v.label}
              </button>
            ))}
          </div>

          <div className="fp-tq-list">
            {HR_QUESTIONS.slice(0, hrView).map((q, i) => (
              <div key={i} className="fp-tq">
                <span className="fp-tq-rank">{i + 1}</span>
                <div className="fp-tq-body">
                  <div className="fp-tq-text">{q}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
