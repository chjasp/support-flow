export type Sender = "user" | "bot";

export type Message = {
  id: string;
  text: string;
  sender: Sender;
  timestamp: string;
};

export type ChatMetadata = {
  id:string;
  title: string;
  lastActivity: string;
}; 