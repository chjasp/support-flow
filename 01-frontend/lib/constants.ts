export const MAX_TITLE_LENGTH = 30;
export const SIDEBAR_TITLE_LIMIT = 20;
export const TYPING_INTERVAL_MS = 8;

export const CHATS_ENDPOINT = '/api/chats';
export const getMessagesEndpoint = (chatId: string) => `${CHATS_ENDPOINT}/${chatId}/messages`;
export const postMessageEndpoint = (chatId: string) => `${CHATS_ENDPOINT}/${chatId}/messages`;
export const streamMessageEndpoint = (chatId: string) => `${CHATS_ENDPOINT}/${chatId}/messages/stream`;
export const deleteChatEndpoint = (chatId: string) => `${CHATS_ENDPOINT}/${chatId}`; 