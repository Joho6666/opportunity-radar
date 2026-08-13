insert into public.sources(slug,name,type,status) values ('mock','Mock 数据源','mock','available'),('public_web','公开网页','web','unavailable') on conflict (slug) do nothing;
