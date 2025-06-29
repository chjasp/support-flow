export const MAX_TITLE_LENGTH = 30;
export const SIDEBAR_TITLE_LIMIT = 20;
export const TYPING_INTERVAL_MS = 8;

export const NOTEBOOKS_ENDPOINT = '/api/notebooks';
export const getMessagesEndpoint = (notebookId: string) => `${NOTEBOOKS_ENDPOINT}/${notebookId}/messages`;
export const postMessageEndpoint = (notebookId: string) => `${NOTEBOOKS_ENDPOINT}/${notebookId}/messages`;
export const deleteNotebookEndpoint = (notebookId: string) => `${NOTEBOOKS_ENDPOINT}/${notebookId}`;

// Models
export const MODELS_ENDPOINT = '/api/models'; 