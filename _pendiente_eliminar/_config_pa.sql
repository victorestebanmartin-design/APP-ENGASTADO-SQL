-- Configuración exportada de BD local
-- Ejecutar en PythonAnywhere para sincronizar puestos/máquinas


-- carros
INSERT OR IGNORE INTO carros (numero,bono_id,estado,fecha_inicio,fecha_fin,progreso,ordenes_totales,ordenes_completadas,created_at,updated_at) VALUES (1,NULL,'disponible',NULL,NULL,0.0,0,0,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO carros (numero,bono_id,estado,fecha_inicio,fecha_fin,progreso,ordenes_totales,ordenes_completadas,created_at,updated_at) VALUES (2,NULL,'disponible',NULL,NULL,0.0,0,0,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO carros (numero,bono_id,estado,fecha_inicio,fecha_fin,progreso,ordenes_totales,ordenes_completadas,created_at,updated_at) VALUES (3,NULL,'disponible',NULL,NULL,0.0,0,0,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO carros (numero,bono_id,estado,fecha_inicio,fecha_fin,progreso,ordenes_totales,ordenes_completadas,created_at,updated_at) VALUES (4,NULL,'disponible',NULL,NULL,0.0,0,0,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO carros (numero,bono_id,estado,fecha_inicio,fecha_fin,progreso,ordenes_totales,ordenes_completadas,created_at,updated_at) VALUES (5,NULL,'disponible',NULL,NULL,0.0,0,0,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO carros (numero,bono_id,estado,fecha_inicio,fecha_fin,progreso,ordenes_totales,ordenes_completadas,created_at,updated_at) VALUES (6,NULL,'disponible',NULL,NULL,0.0,0,0,'2026-02-18 15:43:41','2026-02-18 15:43:41');

-- maquinas
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('965d3fd8-a303-43e9-8697-73c7c69af473','puesto_001','AMP ROJA','AMP (47386) (TERMINALES ROJOS)','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('0560d7b0-bd18-49cb-9671-edda662adbae','puesto_001','AMP AZUL','KOMAX Alpha 455','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('5ebe085f-3839-4a71-96de-d0f5dd626ba0','puesto_001','AMP AMARILLOS','','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('10823d83-f9ee-4645-ae00-6dfec2ec91c4','puesto_002','Harting 1mm','Pines 1mm','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('50be0819-3273-4379-bdf3-fcde7d769fc3','puesto_002','Harting 0,5mm','Pines 0,5mm','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('d748360d-af71-4e06-8896-9465b5c76b87','puesto_3','PUNTERAS','','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('a4d166c9-8b53-4d7c-9992-44f031544786','puesto_3','WEIDMULLEER PZ10','','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('e7fc8ea4-c3d9-48cc-abed-9297da959c80','puesto_4','DMC AZUL SH463','','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('1de662fd-4d78-4921-a490-266cfc283fb3','puesto_4','TAMBOR VERDE E','','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('53411894-adea-4aa5-aa5e-1c554d8f6213','puesto_4','TAMBOR ROJO','','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('243866c8-31fa-4eac-b888-3ccd43378c82','puesto_4','AMP SIMABLOCK','','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('7bcff112-ee20-4345-b29f-102f7dc5faa2','puesto_4','DMC AZUL TH163','','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('81651463-341f-46c1-9c1a-26232d87babb','puesto_4','HARTING AZUL','','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('34ca90f9-0a1f-427e-9045-c9a8f4362649','puesto_4','POWER SIGNAL','','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('47dd5926-0caf-4737-9cf9-8e1224e3259f','puesto_4','TAMBOR VERDE C','','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('db1dae58-eaf1-4768-9b74-7bda5088c24e','puesto_4','TAMBOR VERDE D','','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('maq_017','puesto_005','TH1','ROJA','',1,'2026-04-28 10:24:24','2026-04-28 10:24:24');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('maq_018','puesto_005','TH2','AZUL','',1,'2026-04-28 10:24:42','2026-04-28 10:24:42');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('maq_019','puesto_005','TH3','AMARILLA','',1,'2026-04-28 10:25:09','2026-04-28 10:25:09');
INSERT OR IGNORE INTO maquinas (id,puesto_id,nombre,modelo,descripcion,activo,created_at,updated_at) VALUES ('maq_020','puesto_005','TH3-2','AMARILLA AISLANTE GRUESO','',1,'2026-04-28 10:25:30','2026-04-28 10:25:30');

-- maquinas_terminales
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (1,'965d3fd8-a303-43e9-8697-73c7c69af473','640204',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (2,'965d3fd8-a303-43e9-8697-73c7c69af473','640243',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (3,'965d3fd8-a303-43e9-8697-73c7c69af473','640210',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (4,'965d3fd8-a303-43e9-8697-73c7c69af473','640230',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (5,'965d3fd8-a303-43e9-8697-73c7c69af473','640243A',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (6,'965d3fd8-a303-43e9-8697-73c7c69af473','641H002',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (7,'965d3fd8-a303-43e9-8697-73c7c69af473','641H039',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (8,'965d3fd8-a303-43e9-8697-73c7c69af473','641H056',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (9,'965d3fd8-a303-43e9-8697-73c7c69af473','640260',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (10,'0560d7b0-bd18-49cb-9671-edda662adbae','640205',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (11,'0560d7b0-bd18-49cb-9671-edda662adbae','640211',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (12,'0560d7b0-bd18-49cb-9671-edda662adbae','640261',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (13,'5ebe085f-3839-4a71-96de-d0f5dd626ba0','640245',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (14,'5ebe085f-3839-4a71-96de-d0f5dd626ba0','640206',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (15,'5ebe085f-3839-4a71-96de-d0f5dd626ba0','640209',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (16,'5ebe085f-3839-4a71-96de-d0f5dd626ba0','640212',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (17,'5ebe085f-3839-4a71-96de-d0f5dd626ba0','641H057',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (18,'10823d83-f9ee-4645-ae00-6dfec2ec91c4','641M155',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (19,'50be0819-3273-4379-bdf3-fcde7d769fc3','641M10100',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (20,'d748360d-af71-4e06-8896-9465b5c76b87','641H10055',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (21,'d748360d-af71-4e06-8896-9465b5c76b87','641H10057',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (22,'d748360d-af71-4e06-8896-9465b5c76b87','641H10058',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (23,'d748360d-af71-4e06-8896-9465b5c76b87','641H10056',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (24,'a4d166c9-8b53-4d7c-9992-44f031544786','H0337649',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (25,'e7fc8ea4-c3d9-48cc-abed-9297da959c80','641M10293',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (26,'e7fc8ea4-c3d9-48cc-abed-9297da959c80','641M10295',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (27,'e7fc8ea4-c3d9-48cc-abed-9297da959c80','641M10292',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (28,'1de662fd-4d78-4921-a490-266cfc283fb3','641M600',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (29,'1de662fd-4d78-4921-a490-266cfc283fb3','641M082',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (30,'1de662fd-4d78-4921-a490-266cfc283fb3','641M644',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (31,'1de662fd-4d78-4921-a490-266cfc283fb3','641M026',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (32,'1de662fd-4d78-4921-a490-266cfc283fb3','641M027',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (33,'1de662fd-4d78-4921-a490-266cfc283fb3','641M645',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (34,'1de662fd-4d78-4921-a490-266cfc283fb3','641M532',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (35,'53411894-adea-4aa5-aa5e-1c554d8f6213','641M937',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (36,'53411894-adea-4aa5-aa5e-1c554d8f6213','641M936',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (37,'243866c8-31fa-4eac-b888-3ccd43378c82','640304D',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (38,'243866c8-31fa-4eac-b888-3ccd43378c82','640305',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (39,'7bcff112-ee20-4345-b29f-102f7dc5faa2','641M10196',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (40,'81651463-341f-46c1-9c1a-26232d87babb','641M10091',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (41,'81651463-341f-46c1-9c1a-26232d87babb','641M239',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (42,'34ca90f9-0a1f-427e-9045-c9a8f4362649','641M10045',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (43,'47dd5926-0caf-4737-9cf9-8e1224e3259f','641M613',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (44,'db1dae58-eaf1-4768-9b74-7bda5088c24e','641M10078',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (45,'db1dae58-eaf1-4768-9b74-7bda5088c24e','641M577',1,'2026-02-18 15:43:41');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (46,'maq_017','641H10001',1,'2026-04-28 10:26:58');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (47,'maq_017','641H10003',1,'2026-04-28 10:26:58');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (48,'maq_017','641H10006',1,'2026-04-28 10:26:58');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (49,'maq_017','641H10009',1,'2026-04-28 10:26:58');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (50,'maq_017','641H10039',1,'2026-04-28 10:26:58');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (51,'maq_017','641H10043',1,'2026-04-28 10:26:58');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (52,'maq_017','641H10047',1,'2026-04-28 10:26:58');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (53,'maq_017','641H10048',1,'2026-04-28 10:26:58');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (54,'maq_017','641H10069',1,'2026-04-28 10:26:58');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (55,'maq_017','641H10014',1,'2026-04-28 10:27:19');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (56,'1de662fd-4d78-4921-a490-266cfc283fb3','641M029',1,'2026-04-28 10:28:02');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (57,'db1dae58-eaf1-4768-9b74-7bda5088c24e','641M466',1,'2026-04-28 10:28:53');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (58,'db1dae58-eaf1-4768-9b74-7bda5088c24e','641M531',1,'2026-04-28 10:28:53');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (59,'db1dae58-eaf1-4768-9b74-7bda5088c24e','641M574',1,'2026-04-28 10:28:53');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (60,'db1dae58-eaf1-4768-9b74-7bda5088c24e','641M576',1,'2026-04-28 10:28:53');
INSERT OR IGNORE INTO maquinas_terminales (id,maquina_id,terminal_codigo,activo,created_at) VALUES (61,'47dd5926-0caf-4737-9cf9-8e1224e3259f','641M594',1,'2026-04-28 10:29:16');

-- puestos
INSERT OR IGNORE INTO puestos (id,nombre,descripcion,activo,created_at,updated_at) VALUES ('puesto_001','TERMINALES AMP','Terminales AMP FORRADOS',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO puestos (id,nombre,descripcion,activo,created_at,updated_at) VALUES ('puesto_002','PINES RACK','Puesto secundario línea de producción 2',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO puestos (id,nombre,descripcion,activo,created_at,updated_at) VALUES ('puesto_3','PUNTERAS','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO puestos (id,nombre,descripcion,activo,created_at,updated_at) VALUES ('puesto_4','MANUAL','',1,'2026-02-18 15:43:41','2026-02-18 15:43:41');
INSERT OR IGNORE INTO puestos (id,nombre,descripcion,activo,created_at,updated_at) VALUES ('puesto_005','MECATRACION','',1,'2026-04-28 10:23:59','2026-04-28 10:23:59');