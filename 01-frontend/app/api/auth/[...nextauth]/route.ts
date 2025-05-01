import NextAuth from "next-auth"
import GoogleProvider from "next-auth/providers/google"
import type { NextAuthOptions, User, Session } from "next-auth"
import type { JWT } from "next-auth/jwt"

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID as string,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET as string,
    }),
  ],
  secret: process.env.NEXTAUTH_SECRET,
  session: {
    strategy: "jwt", // Use JWTs for session management
  },
  callbacks: {
    // Include the Google ID token in the JWT
    async jwt({ token, account, profile }) {
      if (account?.id_token) {
        token.idToken = account.id_token; // Store the ID token
      }
      // Add user profile info if needed
      if (profile) {
         token.name = profile.name;
         token.email = profile.email;
         token.picture = profile.picture;
      }
      return token;
    },
    // Make the ID token and user info available in the session object client-side
    async session({ session, token }) {
      session.idToken = token.idToken as string; // Pass ID token to session
      if (token.sub && session.user) {
          session.user.id = token.sub; // Standard JWT subject claim
      }
      if (token.email && session.user) {
          session.user.email = token.email;
      }
       if (token.name && session.user) {
          session.user.name = token.name;
      }
       if (token.picture && session.user) {
          session.user.image = token.picture;
      }
      return session;
    },
  },
  // Optional: Add custom pages if needed
  // pages: {
  //   signIn: '/auth/signin',
  // }
}

const handler = NextAuth(authOptions)

export { handler as GET, handler as POST }
