"use server";

import { revalidatePath } from "next/cache";
import { postHumanAction } from "../../lib/review.mjs";

export async function submitReview(kind, id, _previous, formData) {
  const result = await postHumanAction(process.env.API_BASE_URL, kind, id, formData);
  if (!result.error) revalidatePath("/", "layout"); // every page shows Flag/Evidence state
  return result;
}
