import NextAuth, { DefaultSession, DefaultUser, Profile } from "next-auth"
import { JWT, DefaultJWT } from "next-auth/jwt"

declare module "next-auth" {
  interface Session {
    idToken?: string; // Add the idToken field
    user: {
      id?: string | null; // Add id field
    } & DefaultSession["user"];
  }

  interface User extends DefaultUser {
    // Add any custom fields you might add via profile callback
  }

  // Add the Profile interface to include picture
  interface Profile {
    picture?: string | null;
    // Include other fields from Google profile if needed, e.g.:
    // email_verified?: boolean;
    // locale?: string;
    // hd?: string; // Hosted domain for Google Workspace users
  }
}

declare module "next-auth/jwt" {
  interface JWT extends DefaultJWT {
    idToken?: string; // Add the idToken field to the JWT type
    // Add other profile fields if stored in JWT
    picture?: string | null;
  }
} 