"use client"; // Add this directive at the top

import { useSession, signIn } from "next-auth/react"; // Import useSession and signIn
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ArrowRight, Bot, FileUp, MailWarning, Loader2 } from "lucide-react"; // Example icons
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from "recharts" // Import recharts components
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig // Import ChartConfig type
} from "@/components/ui/chart" // Import shadcn chart components
import { useEffect } from "react"; // Import useEffect for redirect
import { useRouter } from "next/navigation"; // Import useRouter for redirect

export default function DashboardPage() {
  const { data: session, status } = useSession(); // Get session status
  const router = useRouter();

  // Redirect if not authenticated
  useEffect(() => {
    if (status === "unauthenticated") {
      // Optionally redirect to a specific sign-in page or show a message
      // For simplicity, we'll just prevent rendering sensitive content below
      // Or redirect: router.push('/api/auth/signin'); // Or a custom signin page
    }
  }, [status, router]);

  // Placeholder data - replace with actual data fetching later
  const emailsToReviewCount = 5;
  const kbDocumentCount = 152;
  const lastUploadStatus = "Completed";
  const lastUploadFile = "Product_Specs_v3.pdf";

  // Sample data for Line Chart (Incoming Mails)
  const mailTrendData = [
    { date: "2024-07-01", count: 12 },
    { date: "2024-07-02", count: 19 },
    { date: "2024-07-03", count: 15 },
    { date: "2024-07-04", count: 25 },
    { date: "2024-07-05", count: 22 },
    { date: "2024-07-06", count: 30 },
    { date: "2024-07-07", count: 28 },
  ];

  // Sample data for Bar Chart (Mails per Category - Last 30 Days)
  const mailCategoryData = [
    { category: "Support", count: 152 },
    { category: "Sales", count: 89 },
    { category: "Billing", count: 45 },
    { category: "Feedback", count: 67 },
    { category: "Other", count: 31 },
  ];

  // Chart config (optional, for tooltip customization etc.)
  const chartConfig = {
    count: {
      label: "Mails",
      color: "hsl(var(--chart-1))", // Use CSS variable for color
    },
  } satisfies ChartConfig // Add ChartConfig type after satisfies

  // Show loading state
  if (status === "loading") {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Show login prompt or restrict content if unauthenticated
  if (status === "unauthenticated") {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <p className="text-lg mb-4">Please sign in to view the dashboard.</p>
        <Button onClick={() => signIn("google")}>Sign In with Google</Button>
      </div>
    );
  }

  // Render dashboard content only if authenticated
  return (
    <div className="px-6">
      <h1 className="text-3xl font-bold tracking-tight mb-6">Dashboard</h1>

      {/* Top Row Cards */}
      <div className="grid gap-4 md:grid-cols-2 mb-6">
        {/* Emails Awaiting Review Card */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Emails Awaiting Review
            </CardTitle>
            <MailWarning className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{emailsToReviewCount}</div>
            <p className="text-xs text-muted-foreground">
              Emails pre-processed and ready for your input.
            </p>
          </CardContent>
          <CardFooter>
            <Button asChild size="sm">
              <Link href="/mail">
                Review Emails <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </CardFooter>
        </Card>

        {/* Knowledge Base Status Card */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Knowledge Base
            </CardTitle>
            {/* Icon could change based on status */}
            <Bot className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{kbDocumentCount} Documents</div>
            <p className="text-xs text-muted-foreground">
              Last Upload: {lastUploadFile} ({lastUploadStatus})
            </p>
          </CardContent>
           <CardFooter className="flex justify-between">
             <Button variant="outline" size="sm" asChild>
               <Link href="/chat">Chat with KB</Link>
             </Button>
             <Button size="sm" asChild>
               <Link href="/knowledge-base"> {/* Or /knowledge-base/upload */}
                 Upload Info <FileUp className="ml-2 h-4 w-4" />
               </Link>
             </Button>
           </CardFooter>
        </Card>

        {/* Add more cards here - e.g., Recent Uploads List, Quick Stats */}

      </div>

      {/* Charts Row */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Incoming Mail Trend Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Incoming Mail Trend (Last 7 Days)</CardTitle>
            <CardDescription>Daily count of incoming emails.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={chartConfig} className="h-[250px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={mailTrendData}
                  margin={{ top: 5, right: 10, left: -20, bottom: 0 }} // Adjusted margins
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickLine={false}
                    axisLine={false}
                    tickMargin={8}
                    tickFormatter={(value) => value.slice(-2)} // Show only day part
                  />
                  <YAxis
                    tickLine={false}
                    axisLine={false}
                    tickMargin={8}
                    width={30} // Give Y-axis labels some space
                  />
                  <ChartTooltip
                    cursor={false} // Disable tooltip cursor line
                    content={<ChartTooltipContent hideLabel />} // Use shadcn tooltip
                  />
                  <Line
                    dataKey="count"
                    type="monotone"
                    stroke="var(--color-primary)" // Use theme color
                    strokeWidth={2}
                    dot={true} // Show dots on data points
                  />
                </LineChart>
              </ResponsiveContainer>
            </ChartContainer>
          </CardContent>
        </Card>

        {/* Mail Categories Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Mail Categories (Last 30 Days)</CardTitle>
            <CardDescription>Distribution of emails by category.</CardDescription>
          </CardHeader>
          <CardContent>
             <ChartContainer config={chartConfig} className="h-[250px] w-full">
               <ResponsiveContainer width="100%" height="100%">
                 <BarChart
                   data={mailCategoryData}
                   layout="vertical" // Make it a horizontal bar chart
                   margin={{ top: 5, right: 10, left: 0, bottom: 0 }} // Adjusted margins
                 >
                   <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                   <YAxis
                     dataKey="category"
                     type="category"
                     tickLine={false}
                     axisLine={false}
                     tickMargin={8}
                     width={80} // Wider margin for category names
                   />
                   <XAxis dataKey="count" type="number" hide /> {/* Hide X axis labels */}
                   <ChartTooltip
                     cursor={false}
                     content={<ChartTooltipContent hideLabel />}
                   />
                   <Bar
                     dataKey="count"
                     fill="var(--color-primary)" // Use theme color
                     radius={4} // Rounded corners for bars
                     barSize={30} // Adjust bar thickness
                   />
                 </BarChart>
               </ResponsiveContainer>
             </ChartContainer>
          </CardContent>
        </Card>
      </div>

      {/* Potentially add a section for Recent Uploads Table later */}
      {/* <div className="mt-6">
        <Card>
          <CardHeader>
            <CardTitle>Recent Uploads</CardTitle>
          </CardHeader>
          <CardContent>
             Placeholder for a Table or List component
            <p>Upload 1 - Completed</p>
            <p>Upload 2 - Processing</p>
            <p>Upload 3 - Failed</p>
          </CardContent>
        </Card>
      </div> */}
    </div>
  );
}
