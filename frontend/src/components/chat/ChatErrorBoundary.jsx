import { Component } from 'react';

// A render error in the conversation or source pane shows a way out, not a blank screen.
export default class ChatErrorBoundary extends Component {
    state = { failed: false };

    static getDerivedStateFromError() {
        return { failed: true };
    }

    componentDidCatch(error) {
        console.error('Chat render error:', error);
    }

    render() {
        if (!this.state.failed) return this.props.children;
        return (
            <div className="cx-crash" role="alert">
                <p>Something went wrong displaying this chat.</p>
                <button type="button" className="cx-btn" onClick={() => window.location.reload()}>Reload</button>
            </div>
        );
    }
}
