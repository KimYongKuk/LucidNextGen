import { NextResponse } from "next/server";

export async function GET(request: Request) {
    return NextResponse.json([]);
}

export async function PATCH(request: Request) {
    return NextResponse.json({ status: "ok" });
}
