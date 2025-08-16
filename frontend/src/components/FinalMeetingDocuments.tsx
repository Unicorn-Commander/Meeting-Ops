import React from 'react';
import {
  FileText,
  ListChecks,
  Clock,
  Users,
  Calendar,
  CheckCircle,
  Flag,
  BarChart,
  MessageSquare,
  Book,
  Target,
  Archive
} from 'lucide-react';

interface FinalMeetingDocumentsProps {
  sessionId: string;
  finalSummary: any;
  transcript: string;
  duration: number;
}

export const FinalMeetingDocuments: React.FC<FinalMeetingDocumentsProps> = ({
  sessionId,
  finalSummary,
  transcript,
  duration
}) => {
  const documents = [
    {
      id: 'executive',
      title: 'Executive Summary',
      icon: FileText,
      color: 'purple',
      content: finalSummary?.executive || 'Comprehensive meeting overview will be generated...'
    },
    {
      id: 'highlights',
      title: 'Meeting Highlights',
      icon: Target,
      color: 'yellow',
      content: finalSummary?.highlights || finalSummary?.bullets || []
    },
    {
      id: 'minutes',
      title: 'Meeting Minutes',
      icon: Book,
      color: 'blue',
      content: finalSummary?.minutes || 'Detailed meeting minutes will be compiled...'
    },
    {
      id: 'bullets',
      title: 'Bullet Point Notes',
      icon: ListChecks,
      color: 'green',
      content: finalSummary?.bullets || []
    },
    {
      id: 'actions',
      title: 'Action Items List',
      icon: Flag,
      color: 'orange',
      content: finalSummary?.actions || []
    },
    {
      id: 'decisions',
      title: 'Decision Log',
      icon: CheckCircle,
      color: 'emerald',
      content: finalSummary?.decisions || []
    },
    {
      id: 'dates',
      title: 'Key Dates & Deadlines',
      icon: Calendar,
      color: 'red',
      content: finalSummary?.deadlines || []
    },
    {
      id: 'timeline',
      title: 'Timeline Summary',
      icon: Clock,
      color: 'indigo',
      content: finalSummary?.timeline || 'Meeting timeline will be analyzed...'
    },
    {
      id: 'topics',
      title: 'Topic-Based Summary',
      icon: BarChart,
      color: 'cyan',
      content: finalSummary?.topics || []
    },
    {
      id: 'participants',
      title: 'Participant Contributions',
      icon: Users,
      color: 'pink',
      content: finalSummary?.participants || {}
    },
    {
      id: 'transcript',
      title: 'Transcript with Timestamps',
      icon: MessageSquare,
      color: 'gray',
      content: transcript || 'Full transcript will be available...'
    },
    {
      id: 'glossary',
      title: 'Glossary & Acronyms',
      icon: Archive,
      color: 'violet',
      content: finalSummary?.glossary || {}
    }
  ];

  const formatContent = (doc: any) => {
    if (typeof doc.content === 'string') {
      return <p className="text-sm text-zinc-100 leading-relaxed">{doc.content}</p>;
    }
    
    if (Array.isArray(doc.content)) {
      return (
        <ul className="space-y-2">
          {doc.content.map((item: any, idx: number) => (
            <li key={idx} className="flex items-start gap-2">
              <span className={`text-${doc.color}-400 mt-0.5`}>•</span>
              <span className="text-sm text-zinc-100">
                {typeof item === 'object' ? item.action || item.text || JSON.stringify(item) : item}
              </span>
            </li>
          ))}
        </ul>
      );
    }
    
    if (typeof doc.content === 'object') {
      return (
        <div className="space-y-2">
          {Object.entries(doc.content).map(([key, value]: [string, any]) => (
            <div key={key} className="flex items-start gap-2">
              <span className="text-sm font-medium text-zinc-300">{key}:</span>
              <span className="text-sm text-zinc-100">{String(value)}</span>
            </div>
          ))}
        </div>
      );
    }
    
    return null;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-white">Final Meeting Documents</h2>
        <div className="flex items-center gap-3">
          <span className="text-sm px-3 py-1 rounded-full bg-green-500/20 text-green-300 border border-green-500/30">
            12 Documents Generated
          </span>
          <span className="text-sm px-3 py-1 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30">
            Granite 3.3 8B
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {documents.map((doc) => {
          const Icon = doc.icon;
          return (
            <div
              key={doc.id}
              className="rounded-xl bg-zinc-900/70 border border-zinc-800 p-4 hover:border-zinc-700 transition-all"
            >
              <div className="flex items-center gap-3 mb-3">
                <div className={`w-8 h-8 rounded-lg bg-${doc.color}-500/20 flex items-center justify-center`}>
                  <Icon className={`w-4 h-4 text-${doc.color}-400`} />
                </div>
                <h3 className="text-sm font-semibold text-white">{doc.title}</h3>
              </div>
              
              <div className="max-h-40 overflow-y-auto scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-zinc-900">
                {formatContent(doc)}
              </div>
              
              <button className="mt-3 w-full px-3 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-zinc-300 transition-colors">
                Export as PDF
              </button>
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-center gap-4 mt-6">
        <button className="px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors">
          Export All Documents
        </button>
        <button className="px-6 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-white rounded-lg font-medium transition-colors">
          Share Meeting Package
        </button>
      </div>
    </div>
  );
};