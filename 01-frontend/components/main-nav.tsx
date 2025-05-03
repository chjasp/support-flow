"use client";

import * as React from "react"
import Link from "next/link"
import { useSession, signIn, signOut } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { LogIn, LogOut, User as UserIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
  navigationMenuTriggerStyle,
} from "@/components/ui/navigation-menu"

export function MainNav({
  className,
  ...props
}: React.HTMLAttributes<HTMLElement>) {
  const { data: session, status } = useSession()
  const isLoading = status === "loading"

  return (
    <div className={cn("flex w-full items-center justify-between px-4", className)} {...props}>
      <div className="flex items-center space-x-6">
        <Link href="/" className="mr-6 flex items-center space-x-2">
          <span className="font-bold sm:inline-block">
            bloomlake
          </span>
        </Link>
        <NavigationMenu>
          <NavigationMenuList>
            <NavigationMenuItem>
              <NavigationMenuLink asChild>
                <Link href="/" className={navigationMenuTriggerStyle()}>
                  Dashboard
                </Link>
              </NavigationMenuLink>
            </NavigationMenuItem>
            <NavigationMenuItem>
              <NavigationMenuLink asChild>
                <Link href="/chat" className={navigationMenuTriggerStyle()}>
                  Chat
                </Link>
              </NavigationMenuLink>
            </NavigationMenuItem>
            <NavigationMenuItem>
              <NavigationMenuLink asChild>
                <Link href="/mail" className={navigationMenuTriggerStyle()}>
                  Mail
                </Link>
              </NavigationMenuLink>
            </NavigationMenuItem>
            <NavigationMenuItem>
              <NavigationMenuLink asChild>
                <Link href="/knowledge-base" className={navigationMenuTriggerStyle()}>
                  Knowledge Base
                </Link>
              </NavigationMenuLink>
            </NavigationMenuItem>
          </NavigationMenuList>
        </NavigationMenu>
      </div>

      <div className="flex items-center space-x-2">
        {isLoading ? (
          <Button variant="outline" size="sm" disabled>Loading...</Button>
        ) : session?.user ? (
          <>
            <span className="text-sm text-muted-foreground hidden sm:inline-block">
              {session.user.name ?? session.user.email}
            </span>
            <Button variant="outline" size="sm" onClick={() => signOut()} className="cursor-pointer">
              <LogOut className="mr-2 h-4 w-4" /> Sign Out
            </Button>
          </>
        ) : (
          <Button variant="default" size="sm" onClick={() => signIn("google")}>
            <LogIn className="mr-2 h-4 w-4" /> Sign In
          </Button>
        )}
      </div>
    </div>
  )
}