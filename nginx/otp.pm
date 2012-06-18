package otp;
#use nginx;
use Data::Dumper;
use JSON;
use LWP::Simple;
use POSIX qw(ceil floor);
use strict;
use warnings;

my @regions;
    my @urls = ('http://localhost:8080/opentripplanner-api-webapp/ws', );

sub init {
    #load up a list of server domains, which it would be nice to get from
    #somewhere sensible but which for now we will hardcode

    @regions = ();
    for my $url (@urls) {
        load_server_data($url);
    }
}

sub make_bbox {
    my $coords = shift;

    my ($minx, $miny, $maxx, $maxy);
    for my $coord ($coords) {
        if (ref $coord->[0] eq 'ARRAY') {
            for my $inner (@$coord) {
                if ($minx) {
                    my ($nminx, $nminy, $nmaxx, $nmaxy) = make_bbox($inner);
                    $minx = $nminx if ($nminx < $minx);
                    $miny = $nminy if ($nminy < $miny);
                    $maxx = $nmaxx if ($nmaxx > $maxx);
                    $maxy = $nmaxy if ($nmaxy > $maxy);
                } else {
                    ($minx, $miny, $maxx, $maxy) = make_bbox($inner);
                }
            }
        } else {
            my ($x, $y) = @$coord;
            if ($miny) {
                $minx = $x if ($x < $minx);
                $miny = $y if ($y < $miny);
                $maxx = $x if ($x > $maxx);
                $maxy = $y if ($y > $maxy);
            } else {
                $minx = $maxx = $x;
                $miny = $maxy = $y;
            }
        }
    }
    return ($minx, $miny, $maxx, $maxy);
}

sub make_bbox_record {
    my $coords = shift;
    my ($minx, $miny, $maxx, $maxy) = make_bbox($coords);
    return scalar {'maxx' => $maxx, 'maxy' => $maxy, 'minx' => $minx, 'miny' => $miny};
}

my $VERTICAL_REGIONS=1000;

sub index_coords {
    my ($coords, $bbox, $index) = @_;

    unless ($index) {
        $index = [];
        for my $i (0..$VERTICAL_REGIONS-1) {
            $index->[$i] = [];
        }
    
    }

    my $min_lat = $bbox->{'miny'};
    my $max_lat = $bbox->{'maxy'};
    my $lat_range = $max_lat - $min_lat;
    my $scaling = $VERTICAL_REGIONS / $lat_range;

    for my $poly ($coords) {
        if (ref $poly->[0]->[0] eq 'ARRAY') {
            for my $inner (@$poly) {
                index_coords($inner, $bbox, $index);
            }
        } else {
            my $n = scalar @$poly;
            for my $i(0..$n - 1) {
                my $lon1 = $poly->[$i]->[0];
                my $lat1 = $poly->[$i]->[1];
                my $lon2 = $poly->[($i+1) % $n]->[0];
                my $lat2 = $poly->[($i+1) % $n]->[1];

                if ($lat1 > $lat2) {
                    ($lat1, $lon1, $lat2, $lon2) = ($lat2, $lon2, $lat1, $lon1);
                }

                my $scaled_lat1 = floor(($lat1 - $min_lat) * $scaling);
                my $scaled_lat2 = ceil(($lat2 - $min_lat) * $scaling);
                for my $y ($scaled_lat1..$scaled_lat2+1) {
                    push @{$index->[$y]}, [$lon1, $lat1, $lon2, $lat2];
                }
            }
        }
    }
    return $index;
}

sub load_server_data {
    my $url = shift;
    my $rurl = $url . '/routers';
    my $content = get $rurl;#, 'Accept' => 'text/json';
    my $json = decode_json $content;
    my $items = $json->{'routerInfo'};
    ROUTER: for my $router(@$items) {
        my $coords = $router->{'RouterInfo'}->{'polygon'}->{'coordinates'};
        #coords is a list of lists of 2-element lists; we would like to check it
        #against the existing regions
        for my $oldregion (@regions) {

            if ($oldregion->{'poly'} ~~ $coords) {
                my $newrouter = {'url' => $url, 
                                 'routerId' => $router->{'id'}};
                push @{$oldregion->{'routers'}}, $newrouter;
                next ROUTER;
            }
        }
        #no existing region
        my $bbox = make_bbox_record($coords);
        my $newrouter = {
            'indexed' => index_coords($coords, $bbox),
            'poly' => $coords, 
            'bbox' => $bbox,
            'routers'=>[{'url' => $url,
                         'routerId' => $router->{'id'}}]};

        push @regions, $newrouter;

    }
}


#figure out which region this point is in
sub get_region {
    my ($lat, $lon) = @_;

    for my $region (@regions) {
      my $poly = $region->{'poly'};
      my $crossings = 0;
      $poly = $poly->[0]; #first polygon, excluding holes
      my $n = scalar @${poly};
      for my $i(0..$n - 1) {
          my $lon1 = $poly->[$i]->[0];
          my $lat1 = $poly->[$i]->[1];
          my $lon2 = $poly->[($i+1) % $n]->[0];
          my $lat2 = $poly->[($i+1) % $n]->[1];
          if ($lat1 > $lat2) {
              ($lat1, $lon1, $lat2, $lon2) = ($lat2, $lon2, $lat1, $lon1);
          }

          if ($lat1 <= $lat && $lat < $lat2) {
              my $p = ($lat - $lat1) / ($lat2 - $lat1);
              my $lonp = $p * ($lon2 - $lon1) + $lon1;
              if ($lonp > $lon) {
                  $crossings += 1;
              }
          }
      }
      if ($crossings % 2 == 1) {
          return $region;
      }
    }
}

sub get_region_indexed {
    my ($lat, $lon) = @_;

    for my $region (@regions) {
      my $bbox = $region->{'bbox'};
      my ($minx, $miny, $maxx, $maxy) = ($bbox->{'minx'}, 
                                         $bbox->{'miny'}, 
                                         $bbox->{'maxx'}, 
                                         $bbox->{'maxy'});

      next if ($minx > $lon || $maxx < $lon || $miny > $lat || $maxy < $lat);
      
      my $indexed = $region->{'indexed'};

      my $lat_range = $maxy - $miny;
      my $scaling = $VERTICAL_REGIONS / $lat_range;
      my $index = int ($scaling * ($lat - $miny));

      my $crossings = 0;
      for my $seg (@{$indexed->[$index]}) {
          my ($lon1, $lat1, $lon2, $lat2) = @$seg;
          if ($lat1 <= $lat && $lat < $lat2) {
              my $p = ($lat - $lat1) / ($lat2 - $lat1);
              my $lonp = $p * ($lon2 - $lon1) + $lon1;
              if ($lonp > $lon) {
                  $crossings += 1;
              }
          }
      }
      if ($crossings % 2 == 1) {
          #return $region;
          print Dumper $region->{'routers'}
      }
    }
}


sub test {
    init();
    print "nonindexed: " . get_region(41.5, -73.1) . "\n";
    print "indexed: " . get_region_indexed(45.5, -122.91) . "\n";
}

sub handler {
  my $r = shift;

  if ($r->header_only) {
      $r->send_http_header("text/html");
      #return OK;
  }
  
  if (!@regions) {
      init;
  }

  my @query = split(/&/, $r->args);
  my %args;
  foreach my $pair (@query){
      my ($arg, $value) = split(/=/, $pair);
      $value =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
      $args{$arg} = $value; 
  }


  my $from = $args{'fromPlace'};
  $from =~ s/^(.*):://;

  my ($lat,$lon) = split /,/, $from;

  my $region = get_region_indexed($lat, $lon);

  if ($region) {
      my $nrouters = scalar @{$region->{'routers'}};
      my $router = $region->{'routers'}->[int(rand($nrouters))];
      my $url = $router->{url} . '?'. $r->args . "&routerId=" . $router->{routerId};
      $r->send_http_header("text/html"); 
      $r->print($url);
  } else {
      $r->send_http_header("text/html");
      $r->print("$lat, $lon is out of range; ");
  }
  #return OK;
}
 
1;
__END__
