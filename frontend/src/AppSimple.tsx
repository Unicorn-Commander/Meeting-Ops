import React from 'react';
import { HashRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';

const ShowLocation = () => {
  const location = useLocation();
  return <div className="text-yellow-400">Current path: {location.pathname}</div>;
};

const Home = () => <div className="text-white text-2xl">HOME PAGE</div>;
const Recording = () => <div className="text-white text-2xl">RECORDING PAGE</div>;
const Meetings = () => <div className="text-white text-2xl">MEETINGS PAGE</div>;

export function AppSimple() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-900 p-8">
        <h1 className="text-white text-3xl mb-4">Navigation Test</h1>
        <ShowLocation />
        
        <nav className="flex gap-4 mb-8">
          <Link to="/" className="px-4 py-2 bg-blue-600 text-white rounded">Home</Link>
          <Link to="/recording" className="px-4 py-2 bg-green-600 text-white rounded">Recording</Link>
          <Link to="/meetings" className="px-4 py-2 bg-purple-600 text-white rounded">Meetings</Link>
        </nav>

        <div className="bg-gray-800 p-4 rounded">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/recording" element={<Recording />} />
            <Route path="/meetings" element={<Meetings />} />
          </Routes>
        </div>
      </div>
    </Router>
  );
}