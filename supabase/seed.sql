insert into public.sources(slug,name,type,status) values
  ('mock','Mock 数据源','mock','available'),
  ('public_web','公开网页','web','available'),
  ('github','GitHub','github','available'),
  ('hackernews','Hacker News','web','available'),
  ('rss','RSS','rss','available'),
  ('web_search','Web Search','web','available')
on conflict (slug) do nothing;
