import { Brain } from 'lucide-react';
import { useEffect, useState } from 'react';

export default function SplashLoader({ fadeOut }) {
  const [showText, setShowText] = useState(false);
  const [showBar, setShowBar] = useState(false);

  useEffect(() => {
    // Stage 1: Logo fades in immediately
    // Stage 2: Title fades/slides up after 500ms
    const timerText = setTimeout(() => setShowText(true), 500);
    // Stage 3: Glowing loader bar appears after 1000ms
    const timerBar = setTimeout(() => setShowBar(true), 1000);

    return () => {
      clearTimeout(timerText);
      clearTimeout(timerBar);
    };
  }, []);

  return (
    <div className={`splash-container ${fadeOut ? 'fade-out' : ''}`}>
      <div className="splash-content">
        <div className="splash-logo-wrapper">
          <Brain size={64} className="splash-logo-icon" />
          <div className="splash-logo-glow"></div>
        </div>
        
        <h1 className={`splash-title ${showText ? 'visible' : ''}`}>
          <span>Placement</span> <span>Buddy</span> <span className="highlight">Puddy</span>
        </h1>
        
        <div className={`splash-loader-wrapper ${showBar ? 'visible' : ''}`}>
          <div className="splash-loader-track">
            <div className="splash-loader-progress"></div>
          </div>
        </div>
      </div>
    </div>
  );
}
