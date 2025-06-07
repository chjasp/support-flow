"use client";

import * as React from "react"
import Link from "next/link"
import { useSession, signIn, signOut } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { LogIn, LogOut } from "lucide-react"

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
    <div className={cn("flex w-full items-center justify-between", className)} {...props}>
      <div className="flex items-center space-x-6">
        <Link href="/" className="mr-6 flex items-center space-x-2">
          <span className="font-semibold text-chatgpt text-base">
            bloomlake
          </span>
        </Link>
        <NavigationMenu>
          <NavigationMenuList>
            <NavigationMenuItem>
              <NavigationMenuLink asChild>
                <Link href="/" className={cn(
                  navigationMenuTriggerStyle(),
                  "text-chatgpt hover:bg-chatgpt-hover hover:text-chatgpt bg-transparent text-sm font-medium"
                )}>
                  Chat
                </Link>
              </NavigationMenuLink>
            </NavigationMenuItem>
            <NavigationMenuItem>
              <NavigationMenuLink asChild>
                <Link href="/knowledge-base" className={cn(
                  navigationMenuTriggerStyle(),
                  "text-chatgpt hover:bg-chatgpt-hover hover:text-chatgpt bg-transparent text-sm font-medium"
                )}>
                  Upload
                </Link>
              </NavigationMenuLink>
            </NavigationMenuItem>
          </NavigationMenuList>
        </NavigationMenu>
      </div>

      <div className="flex items-center space-x-3">
        {isLoading ? (
          <Button 
            variant="outline" 
            size="sm" 
            disabled 
            className="bg-transparent border-chatgpt text-chatgpt text-xs"
          >
            Loading...
          </Button>
        ) : session?.user ? (
          <>
            <span className="text-xs text-chatgpt-secondary hidden sm:inline-block">
              {session.user.name ?? session.user.email}
            </span>
            <Button 
              variant="outline" 
              size="sm" 
              onClick={() => signOut()} 
              className="cursor-pointer bg-transparent border-chatgpt text-chatgpt hover:bg-chatgpt-hover hover:text-chatgpt text-xs h-8"
            >
              <LogOut className="mr-1.5 h-3 w-3" /> Sign Out
            </Button>
          </>
        ) : (
          <Button
            variant="default"
            size="sm"
            onClick={() => signIn("google", { callbackUrl: "/" })}
            className="chatgpt-button hover:bg-[#16A669] text-xs h-8 font-medium"
          >
            <LogIn className="mr-1.5 h-3 w-3" /> Sign In
          </Button>
        )}
      </div>
    </div>
  )
}