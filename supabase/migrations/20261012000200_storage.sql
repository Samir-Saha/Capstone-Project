-- Private bucket for uploaded course material and resumes.
-- Object paths are "<user id>/<course id>/<file>", so the first folder is the owner.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('course-material', 'course-material', false, 26214400, array['application/pdf'])
on conflict (id) do nothing;

create policy "own material: read" on storage.objects for select to authenticated
  using (bucket_id = 'course-material' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "own material: upload" on storage.objects for insert to authenticated
  with check (bucket_id = 'course-material' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "own material: delete" on storage.objects for delete to authenticated
  using (bucket_id = 'course-material' and (storage.foldername(name))[1] = auth.uid()::text);
