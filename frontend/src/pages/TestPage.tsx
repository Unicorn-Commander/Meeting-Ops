import React from 'react';

export const TestPage: React.FC = () => {
  return (
    <div className="bg-gray-800 rounded-lg p-6">
      <h1 className="text-3xl text-white mb-4">🎉 Test Page Working!</h1>
      <p className="text-gray-300">
        If you can see this, then routing is working correctly!
      </p>
      <div className="mt-4 p-4 bg-green-600 text-white rounded">
        ✅ Success! The new pages are loading.
      </div>
    </div>
  );
};