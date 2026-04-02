//! Benchmarks for map matching performance

use criterion::{black_box, criterion_group, criterion_main, Criterion, BenchmarkId};

// Import from the library
use map_matching::geometry::{haversine_distance, haversine_distance_batch, point_to_line_distance};
use map_matching::spatial_index::SpatialIndex;
use map_matching::viterbi::{viterbi_match, DirectionCache, SegmentCache};

fn bench_haversine_single(c: &mut Criterion) {
    c.bench_function("haversine_single", |b| {
        b.iter(|| {
            haversine_distance(
                black_box(-33.4489),
                black_box(-70.6693),
                black_box(-33.0472),
                black_box(-71.6127),
            )
        })
    });
}

fn bench_haversine_batch(c: &mut Criterion) {
    let mut group = c.benchmark_group("haversine_batch");
    
    for size in [10, 100, 1000, 10000].iter() {
        let lats1: Vec<f64> = (0..*size).map(|i| -33.0 + (i as f64) * 0.001).collect();
        let lons1: Vec<f64> = (0..*size).map(|i| -70.0 + (i as f64) * 0.001).collect();
        let lats2: Vec<f64> = (0..*size).map(|i| -33.1 + (i as f64) * 0.001).collect();
        let lons2: Vec<f64> = (0..*size).map(|i| -70.1 + (i as f64) * 0.001).collect();
        
        group.bench_with_input(BenchmarkId::from_parameter(size), size, |b, _| {
            b.iter(|| {
                haversine_distance_batch(
                    black_box(&lats1),
                    black_box(&lons1),
                    black_box(&lats2),
                    black_box(&lons2),
                )
            })
        });
    }
    
    group.finish();
}

fn bench_point_to_line(c: &mut Criterion) {
    let line = vec![
        (-70.66, -33.45),
        (-70.65, -33.45),
        (-70.64, -33.45),
        (-70.63, -33.45),
    ];
    
    c.bench_function("point_to_line", |b| {
        b.iter(|| {
            point_to_line_distance(
                black_box(-33.4501),
                black_box(-70.648),
                black_box(&line),
            )
        })
    });
}

fn bench_spatial_index_query(c: &mut Criterion) {
    // Create a realistic spatial index
    let n_segments = 1000;
    let segment_pks: Vec<i64> = (0..n_segments).collect();
    let geometries: Vec<Vec<(f64, f64)>> = (0..n_segments)
        .map(|i| {
            let base_lon = -70.7 + (i % 100) as f64 * 0.002;
            let base_lat = -33.5 + (i / 100) as f64 * 0.002;
            vec![
                (base_lon, base_lat),
                (base_lon + 0.001, base_lat),
            ]
        })
        .collect();
    
    let index = SpatialIndex::new(&segment_pks, &geometries, 20.0, true).unwrap();
    
    c.bench_function("spatial_index_query", |b| {
        b.iter(|| {
            index.query(black_box(-70.65), black_box(-33.45), black_box(200.0))
        })
    });
}

fn bench_viterbi(c: &mut Criterion) {
    // Create test data
    let segment_pks: Vec<i64> = (0..100).collect();
    let directions: Vec<i32> = (0..100).map(|_| 0).collect();
    let geometries: Vec<Vec<(f64, f64)>> = (0..100)
        .map(|i| {
            let base_lon = -70.7 + (i as f64) * 0.001;
            vec![
                (base_lon, -33.45),
                (base_lon + 0.001, -33.45),
            ]
        })
        .collect();
    let bearings: Vec<Option<f64>> = (0..100).map(|_| Some(90.0)).collect();
    
    let spatial_index = SpatialIndex::new(&segment_pks, &geometries, 20.0, true).unwrap();
    let direction_cache = DirectionCache::new(&segment_pks, &directions, &geometries).unwrap();
    let segment_cache = SegmentCache::new(&segment_pks, &geometries, &bearings).unwrap();
    
    let mut group = c.benchmark_group("viterbi");
    
    for n_points in [10, 50, 100, 200].iter() {
        let gps_lons: Vec<f64> = (0..*n_points)
            .map(|i| -70.698 + (i as f64) * 0.001)
            .collect();
        let gps_lats: Vec<f64> = (0..*n_points)
            .map(|_| -33.4501)
            .collect();
        
        group.bench_with_input(BenchmarkId::from_parameter(n_points), n_points, |b, _| {
            b.iter(|| {
                viterbi_match(
                    black_box(&gps_lons),
                    black_box(&gps_lats),
                    black_box(&spatial_index),
                    black_box(&direction_cache),
                    black_box(&segment_cache),
                    200.0,
                    25.0,
                    40.0,
                    2,
                    None,
                    30.0,
                    0.5,
                    None,
                )
            })
        });
    }
    
    group.finish();
}

criterion_group!(
    benches,
    bench_haversine_single,
    bench_haversine_batch,
    bench_point_to_line,
    bench_spatial_index_query,
    bench_viterbi,
);

criterion_main!(benches);
