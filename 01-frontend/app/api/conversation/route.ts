import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import OpenAI from "openai";
const client = new OpenAI();

export async function POST(req: Request) {

    try {

        const { userId } = await auth();
        const body = await req.json();
        const { messages } = body

        if (!userId) {
            return new NextResponse("Unauthorized", { status: 401 });
        }

        if (!process.env.OPENAI_API_KEY) {
            return new NextResponse("OpenAI API Key not configured", { status: 500 });
        }

        if (!messages) {
            return new NextResponse("Messages are required", { status: 400 });
        }

        const response = await client.responses.create({
            model: "gpt-4o",
            input: messages
        });

        console.log(response.output_text);

        return NextResponse.json(response.output_text);
    } catch (error) {
        console.error("[CONVERSATION ERROR]", error);
        return new NextResponse("Internal Server Error", { status: 500 });
    };
};