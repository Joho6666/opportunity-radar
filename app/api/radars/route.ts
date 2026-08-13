import { NextResponse } from "next/server"; import { mockRadars } from "@/data/mock-radars"; export async function GET(){return NextResponse.json(mockRadars);}
