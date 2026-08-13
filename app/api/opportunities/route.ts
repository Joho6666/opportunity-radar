import { NextResponse } from "next/server"; import { mockOpportunities } from "@/data/mock-opportunities"; export async function GET(){return NextResponse.json(mockOpportunities);}
